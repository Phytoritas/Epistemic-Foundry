"""Cartography integration gate: map correctness, ranking separation, staleness.

M05 builds the map.  It answers, correctly and on its own terms, where a
candidate sits, how concentrated the population is, and what a change would
touch.  What it cannot answer is whether the map is still *true of the archive*
— the map and the archive are two surfaces over one population, and nothing so
far compares them.  Three failures live in that gap.

The first is disagreement.  A niche can list an occupant the archive never
recorded, or an archive entry can name a cell whose occupant list has never
heard of it; either way one surface is describing a search the other is not
running.  This module refuses on the exact divergent pairs rather than on a
count, because "the map and the archive disagree about 3 candidates" is not
something anyone can act on.

The second is a ranking figure acquiring authority it was never given.  A
coverage ratio and a lineage entropy order a search; a combined score orders a
search.  EF4-I45 says none of them promotes.  So a promotion request that names
a map figure and nothing else is refused here — not because the figure is
wrong, but because a figure that can only rank has been asked to decide.  A map
figure may inform a request; the request must still name gate or parliament
artifacts as what actually justifies it.

The third is staleness that propagates silently.  A map is built for one
generation.  Serving it against a later generation's archive is not merely
out of date: every record derived from it — the coverage map built from those
niches, the blast radius built from that occupancy — inherited the same stale
picture.  So a generation mismatch produces a cascade naming each derived
record that must be rebuilt, rather than a single warning about the map.

What M06 does *not* decide
--------------------------
* It does not promote, and does not evaluate whether a cited gate decision or
  parliament adjudication actually supports promotion.  It checks only that
  authority artifacts were named and that no map figure stood in for them.  The
  promotion decision itself belongs to the P-phase governance surface.
* It does not build, repair, re-place or evict anything on the map.  Every
  divergence is reported against inputs it leaves unmodified.
* It does not interpret an archive entry's class.  Whether an elite cell's
  entry is classed as an elite is the archive's judgement, and restating that
  vocabulary here would duplicate a wire literal (EF4-I22).
* It does not rebuild the records a staleness cascade names.  The cascade is a
  list of work, not the work.

Everything published is re-derivable from its own fields: no clock is read, and
an identifier is minted only when the caller supplies none.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...contracts import default_registry, validate_artifact
from ...domain.hashing import canonical_json, hash_excluding
from ...domain.ids import new_id
from ..v4_m05 import CartographyError, NicheMap

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ARCHIVE_ENTRY_DUPLICATED": (
        "two archive entries claim the same candidate, so the archive has no "
        "single answer to compare the map against"
    ),
    "AUTHORITY_SCHEMA_UNKNOWN": (
        "a schema this gate treats as carrying promotion authority is absent "
        "from the canonical registry, so the ranking separation check would "
        "silently guard nothing"
    ),
    "CITATION_UNRESOLVED": (
        "a promotion request cites a source or figure that neither supplied "
        "map record publishes and no canonical schema declares, so the "
        "citation cannot be checked against anything"
    ),
    "DERIVATION_UNRECORDED": (
        "a downstream record does not declare which map revision it was built "
        "from, so whether a stale map propagated into it cannot be decided"
    ),
    "ELITE_NOT_OCCUPANT": (
        "a niche names an elite that is not among its own occupants, so the "
        "cell's best result is not in the cell"
    ),
    "ELITE_UNARCHIVED": (
        "a niche names an elite the archive holds no entry for, so the cell's "
        "best result exists on the map and nowhere else"
    ),
    "ENTRY_NICHE_UNMAPPED": (
        "an archive entry names a niche id the map does not hold, so the entry "
        "is filed against a cell that does not exist"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "attest agreement between surfaces it never read"
    ),
    "MAP_ENTRY_DIVERGENT": (
        "an archive entry and the map place the same candidate in different "
        "cells, so the two surfaces describe different searches"
    ),
    "MAP_GENERATION_STALE": (
        "a map revision built for one generation is being served against "
        "another, and every record derived from it inherited that picture"
    ),
    "OCCUPANT_UNARCHIVED": (
        "a niche lists an occupant the archive holds no entry for, so the map "
        "counts coverage the archive cannot account for"
    ),
    "PROMOTION_AUTHORITY_ABSENT": (
        "a promotion request rests on ranking figures alone; a combined score, "
        "coverage ratio or entropy may order a search but cannot promote "
        "(EF4-I45), and the request names no gate or parliament artifact"
    ),
    "RANKING_FIGURE_FORGED": (
        "a promotion request quotes a map figure that disagrees with the "
        "record it claims to have read it from"
    ),
    "RECORD_IDENTITY_FORGED": (
        "a record's published hash does not re-derive from its own fields, so "
        "it claims content it does not actually carry"
    ),
}

#: Figures that order a search.  EF4-I45: any of these may *inform* a promotion
#: request; none of them may justify one.  All but the combined score are
#: published field names of the records M05 and the archive builder emit, so a
#: renamed field breaks the schema suite rather than quietly un-guarding a
#: figure.  The combined score is named here even though no map record publishes
#: it, because it is the scalar the invariant is actually about.
RANKING_FIGURE_NAMES: tuple[str, ...] = (
    "combined_score",
    "coverage_ratio",
    "dominant_lineage_share",
    "effective_lineage_count",
    "lineage_entropy",
    "model_entropy",
    "occupied_niches",
    "operator_entropy",
)

#: The one ranking figure with no map record behind it.
EXTERNAL_RANKING_FIGURE = RANKING_FIGURE_NAMES[0]

#: Canonical schemas whose artifacts may carry promotion authority: the gate
#: decisions and the parliament adjudication.  These are registry names rather
#: than a vocabulary of this module's own, and the registry is consulted on
#: every audit so a renamed or removed schema fails loudly here.
AUTHORITY_SCHEMA_NAMES: tuple[str, ...] = ("adjudication", "gate-decision")

#: Downstream record kinds a map revision can propagate into, with the hash and
#: identifier field each one publishes.  A blast radius has no identifier of its
#: own — it is computed for one candidate — so that candidate names it.
DERIVED_RECORD_FIELDS: dict[str, tuple[str, str]] = {
    "blast_radius": ("radius_hash", "candidate_id"),
    "coverage_map": ("map_hash", "map_id"),
    "lineage_diversity_report": ("report_hash", "report_id"),
}

#: The keys a derivation binding must carry to be judged by a cascade.
DERIVATION_FIELDS: tuple[str, ...] = (
    "record_hash",
    "record_id",
    "record_kind",
    "source_generation",
    "source_revision_hash",
)


class CartographyIntegrationError(CartographyError):
    """Two cartographic surfaces disagree, or one claims authority it lacks.

    It subclasses M05's refusal deliberately: a caller that already handles a
    cartographic refusal must not silently miss an integration refusal, and the
    two remain distinguishable by type when the difference matters.
    """


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise CartographyIntegrationError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise CartographyIntegrationError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _finding(code: str, **fields: Any) -> dict[str, Any]:
    """One divergence, carrying the reason its code exists."""
    return {"code": code, "reason": FINDING_CODES[code], **fields}


def _sort_key(row: Mapping[str, Any]) -> tuple[str, bytes]:
    return (str(row["code"]), canonical_json(row))


def _binding_order(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Kind then identifier: a rebuild list a reader can work down in order."""
    return (
        str(row["record_kind"]),
        str(row["record_id"]),
        str(row["record_hash"]),
    )


def _verified(record: object, hash_field: str, label: str) -> dict[str, Any]:
    """A copy of `record`, refused unless its published hash re-derives."""
    copied = dict(_require_mapping(record, label))
    if hash_field not in copied:
        _fail(
            "INPUT_INVALID",
            f"{label} publishes no {hash_field}",
            {"hash_field": hash_field, "label": label},
        )
    derived = hash_excluding(copied, hash_field)
    if str(copied[hash_field]) != derived:
        _fail(
            "RECORD_IDENTITY_FORGED",
            f"{label} does not re-derive its own {hash_field}",
            {"derived": derived, "label": label, "stated": str(copied[hash_field])},
        )
    return copied


def _entry_index(
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """candidate_id -> archive entry, refused when the archive is ambiguous."""
    index: dict[str, dict[str, Any]] = {}
    for position, candidate_entry in enumerate(entries):
        entry = dict(_require_mapping(candidate_entry, f"archive_entries[{position}]"))
        validate_artifact("epistemic-archive-entry", entry)
        candidate_id = str(entry["candidate_id"])
        if candidate_id in index:
            _fail(
                "ARCHIVE_ENTRY_DUPLICATED",
                f"two archive entries claim candidate {candidate_id}",
                {
                    "archive_entry_ids": sorted(
                        [
                            str(index[candidate_id]["archive_entry_id"]),
                            str(entry["archive_entry_id"]),
                        ]
                    ),
                    "candidate_id": candidate_id,
                },
            )
        index[candidate_id] = entry
    return index


def map_agreement_findings(
    *,
    niche_map: NicheMap,
    archive_entries: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Every place the map and the archive describe different searches.

    The survey is complete rather than first-failure: a caller fixing one
    divergence at a time would keep re-running against a pair of surfaces that
    is still inconsistent somewhere else.  Nothing is raised here — the gate
    below is what refuses — and neither input is modified.
    """
    index = _entry_index(archive_entries)
    occupancy = niche_map.occupants()
    findings: list[dict[str, Any]] = []

    for candidate_id, entry in index.items():
        entry_niche_id = str(entry["niche_id"])
        if entry_niche_id not in niche_map.niche_ids():
            findings.append(
                _finding(
                    "ENTRY_NICHE_UNMAPPED",
                    archive_entry_id=str(entry["archive_entry_id"]),
                    candidate_id=candidate_id,
                    entry_niche_id=entry_niche_id,
                )
            )
            continue
        if occupancy.get(candidate_id) != entry_niche_id:
            findings.append(
                _finding(
                    "MAP_ENTRY_DIVERGENT",
                    archive_entry_id=str(entry["archive_entry_id"]),
                    candidate_id=candidate_id,
                    entry_niche_id=entry_niche_id,
                    map_niche_id=occupancy.get(candidate_id),
                )
            )

    for candidate_id, niche_id in occupancy.items():
        if candidate_id not in index:
            findings.append(
                _finding(
                    "OCCUPANT_UNARCHIVED",
                    candidate_id=candidate_id,
                    niche_id=niche_id,
                )
            )

    for niche_id in niche_map.niche_ids():
        niche = niche_map.niche(niche_id)
        elite_id = niche["elite_id"]
        if elite_id is None:
            continue
        elite_id = str(elite_id)
        # `NicheMap` accepts pre-built niche mappings that never passed M05's
        # `build_niche`, so the elite-occupancy rule is re-checked here rather
        # than assumed from the cell's construction path.
        if elite_id not in [str(occupant) for occupant in niche["occupant_ids"]]:
            findings.append(
                _finding(
                    "ELITE_NOT_OCCUPANT",
                    elite_id=elite_id,
                    niche_id=niche_id,
                    occupant_ids=[str(occupant) for occupant in niche["occupant_ids"]],
                )
            )
        if elite_id not in index:
            findings.append(
                _finding("ELITE_UNARCHIVED", elite_id=elite_id, niche_id=niche_id)
            )

    return tuple(sorted(findings, key=_sort_key))


def build_map_agreement_record(
    *,
    niche_map: NicheMap,
    archive_entries: Sequence[Mapping[str, Any]],
    record_id: str | None = None,
) -> dict[str, Any]:
    """Attest that the map and the archive describe the same population.

    On any divergence the refusal carries every finding, so the exact divergent
    pairs are named at once.  The raised code is the alphabetically first
    finding's code — a deterministic choice, not a claim that it is the worst
    one; ``context["findings"]`` is the complete answer.
    """
    findings = map_agreement_findings(
        niche_map=niche_map, archive_entries=archive_entries
    )
    if findings:
        _fail(
            str(findings[0]["code"]),
            f"the map and the archive disagree in {len(findings)} place(s)",
            {
                "finding_codes": sorted({str(row["code"]) for row in findings}),
                "findings": [dict(row) for row in findings],
            },
        )

    index = _entry_index(archive_entries)
    occupancy = niche_map.occupants()
    elite_ids = sorted(
        str(niche_map.niche(niche_id)["elite_id"])
        for niche_id in niche_map.niche_ids()
        if niche_map.niche(niche_id)["elite_id"] is not None
    )
    record: dict[str, Any] = {
        "archived_candidate_ids": sorted(index),
        "counts": {
            "archive_entries": len(index),
            "elites": len(elite_ids),
            "niches": len(niche_map.niche_ids()),
            "occupants": len(occupancy),
        },
        "elite_candidate_ids": elite_ids,
        "entry_hashes": {
            candidate_id: str(entry["artifact_hash"])
            for candidate_id, entry in sorted(index.items())
        },
        "niche_ids": list(niche_map.niche_ids()),
        "occupancy": dict(sorted(occupancy.items())),
        "record_id": record_id or new_id("MAR"),
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record


def build_map_revision(
    *,
    niche_map: NicheMap,
    evolution_run_id: str,
    generation: int,
    revision_id: str | None = None,
) -> dict[str, Any]:
    """Bind a map to the generation it was built for.

    A niche carries coordinates and occupants but no generation, so nothing in
    the map itself says which generation it describes.  This record is that
    statement, and it pins the cells and the occupancy it was made from, so a
    downstream record can name exactly the map it inherited.
    """
    if not isinstance(generation, int) or isinstance(generation, bool):
        _fail(
            "INPUT_INVALID",
            "a map revision must declare an integer generation",
            {"generation": generation},
        )
    revision: dict[str, Any] = {
        "evolution_run_id": str(evolution_run_id),
        "generation": int(generation),
        "niche_hashes": {
            niche_id: str(niche_map.niche(niche_id)["niche_hash"])
            for niche_id in niche_map.niche_ids()
        },
        "occupancy": dict(sorted(niche_map.occupants().items())),
        "revision_id": revision_id or new_id("MRV"),
    }
    revision["revision_hash"] = hash_excluding(revision, "revision_hash")
    return revision


def bind_derived_record(
    *,
    record: Mapping[str, Any],
    record_kind: str,
    revision: Mapping[str, Any],
) -> dict[str, Any]:
    """Declare which map revision a downstream record was built from.

    The binding is verified rather than asserted: the record must re-derive its
    own published hash, so a binding cannot point a revision at content that
    has since changed.
    """
    if record_kind not in DERIVED_RECORD_FIELDS:
        _fail(
            "INPUT_INVALID",
            f"{record_kind} is not a derived record kind this gate tracks",
            {"declared": sorted(DERIVED_RECORD_FIELDS), "record_kind": record_kind},
        )
    hash_field, id_field = DERIVED_RECORD_FIELDS[record_kind]
    verified = _verified(record, hash_field, record_kind)
    checked_revision = _verified(revision, "revision_hash", "revision")
    if id_field not in verified:
        _fail(
            "INPUT_INVALID",
            f"a {record_kind} must publish {id_field}",
            {"id_field": id_field, "record_kind": record_kind},
        )
    return {
        "record_hash": str(verified[hash_field]),
        "record_id": str(verified[id_field]),
        "record_kind": record_kind,
        "source_generation": int(checked_revision["generation"]),
        "source_revision_hash": str(checked_revision["revision_hash"]),
    }


def build_staleness_cascade(
    *,
    revision: Mapping[str, Any],
    serving_generation: int,
    derived_records: Sequence[Mapping[str, Any]] = (),
    cascade_id: str | None = None,
) -> dict[str, Any]:
    """What a map revision propagated into, and what must be rebuilt if it slipped.

    A generation mismatch is never confined to the map.  Every record whose
    binding names this revision was built from these niches and this occupancy,
    so when the revision no longer fits the generation being served, each of
    them is listed as work to redo.  When it still fits, the same records are
    reported as bound and the rebuild list is empty: the cascade is the same
    evidence either way, which is what makes the pass case checkable.

    Records bound to some other revision are listed too, unjudged and with
    their own binding hash — this gate was handed one revision and cannot say
    whether another is current.  A cascade that silently dropped them would
    read as if it had cleared them.
    """
    checked = _verified(revision, "revision_hash", "revision")
    if not isinstance(serving_generation, int) or isinstance(serving_generation, bool):
        _fail(
            "INPUT_INVALID",
            "a cascade must name the integer generation being served",
            {"serving_generation": serving_generation},
        )

    bound: list[dict[str, Any]] = []
    unbound: list[dict[str, Any]] = []
    for position, candidate_binding in enumerate(derived_records):
        binding = dict(_require_mapping(candidate_binding, f"derived[{position}]"))
        missing = sorted(set(DERIVATION_FIELDS) - set(binding))
        if missing:
            _fail(
                "DERIVATION_UNRECORDED",
                f"derived record at position {position} declares no full derivation",
                {
                    "missing": missing,
                    "position": position,
                    "required_fields": list(DERIVATION_FIELDS),
                },
            )
        if not str(binding["source_revision_hash"]).strip():
            _fail(
                "DERIVATION_UNRECORDED",
                f"derived record {binding['record_id']} names no source revision",
                {"record_id": str(binding["record_id"])},
            )
        row = {field: binding[field] for field in DERIVATION_FIELDS}
        if str(row["source_revision_hash"]) == str(checked["revision_hash"]):
            bound.append(row)
        else:
            unbound.append(row)

    is_current = int(checked["generation"]) == int(serving_generation)
    ordered_bound = sorted(bound, key=_binding_order)
    cascade: dict[str, Any] = {
        "bound_records": ordered_bound,
        "cascade_id": cascade_id or new_id("MSC"),
        "counts": {
            "bound_records": len(ordered_bound),
            "rebuild_required": 0 if is_current else len(ordered_bound),
            "unbound_records": len(unbound),
        },
        "evolution_run_id": str(checked["evolution_run_id"]),
        "is_current": is_current,
        # The niches and the occupancy the bound records inherited: a coverage
        # map was built from the first, a blast radius from the second.
        "rebuild_required": [] if is_current else ordered_bound,
        "revision_generation": int(checked["generation"]),
        "revision_hash": str(checked["revision_hash"]),
        "revision_id": str(checked["revision_id"]),
        "revision_niche_ids": sorted(checked["niche_hashes"]),
        "revision_occupant_ids": sorted(checked["occupancy"]),
        "serving_generation": int(serving_generation),
        "unbound_records": sorted(unbound, key=_binding_order),
    }
    cascade["cascade_hash"] = hash_excluding(cascade, "cascade_hash")
    return cascade


def require_current_revision(
    *,
    revision: Mapping[str, Any],
    serving_generation: int,
    derived_records: Sequence[Mapping[str, Any]] = (),
    cascade_id: str | None = None,
) -> dict[str, Any]:
    """Refuse to serve a map built for a different generation.

    The refusal carries the cascade, because "the map is stale" is not
    actionable on its own — what a caller needs is the list of derived records
    that inherited it.  On a match the cascade is returned instead, so the
    same evidence exists whether or not the gate refused.
    """
    cascade = build_staleness_cascade(
        revision=revision,
        serving_generation=serving_generation,
        derived_records=derived_records,
        cascade_id=cascade_id,
    )
    if not cascade["is_current"]:
        _fail(
            "MAP_GENERATION_STALE",
            f"map revision {cascade['revision_id']} was built for generation "
            f"{cascade['revision_generation']}, not {cascade['serving_generation']}",
            {"cascade": cascade},
        )
    return cascade


def _authority_schemas() -> tuple[str, ...]:
    """The authority schema names, checked against the canonical registry."""
    known = set(default_registry().names())
    missing = sorted(name for name in AUTHORITY_SCHEMA_NAMES if name not in known)
    if missing:
        _fail(
            "AUTHORITY_SCHEMA_UNKNOWN",
            "the registry does not declare every schema this gate treats as authority",
            {"declared": list(AUTHORITY_SCHEMA_NAMES), "missing": missing},
        )
    return AUTHORITY_SCHEMA_NAMES


def audit_promotion_request(
    *,
    request: Mapping[str, Any],
    coverage_map: Mapping[str, Any],
    diversity_report: Mapping[str, Any],
    record_id: str | None = None,
) -> dict[str, Any]:
    """Prove that no ranking artifact crossed into promotion authority.

    The request is modelled minimally and only as far as this gate can honestly
    read it: an identifier, the candidate, and a flat list of citations.  A
    citation either quotes a figure from one of the two supplied map records, or
    names an artifact by its canonical schema.  The gate resolves both, and
    refuses when the resolved authority set is empty — a coverage ratio, a
    lineage entropy or a combined score may have informed the request, but
    EF4-I45 leaves them unable to justify it.

    Checks run in a fixed order so the refusal names the real problem: shape
    first, then missing authority, then figure accuracy.  A request resting on
    a combined score alone therefore refuses as ``PROMOTION_AUTHORITY_ABSENT``
    rather than as an unresolved citation.

    Nothing here evaluates the cited gate or parliament artifacts.  Whether they
    support promotion is the P-phase decision; this gate only establishes that
    the request is asking the right surfaces.
    """
    authority_schemas = _authority_schemas()
    stated = dict(_require_mapping(request, "request"))
    for field in ("candidate_id", "citations", "request_id"):
        if field not in stated:
            _fail(
                "INPUT_INVALID",
                f"a promotion request must declare {field}",
                {
                    "field": field,
                    "required_fields": ["candidate_id", "citations", "request_id"],
                },
            )
    citations = stated["citations"]
    if not isinstance(citations, Sequence) or isinstance(citations, (str, bytes)):
        _fail(
            "INPUT_INVALID",
            "a promotion request's citations must be a sequence",
            {"citations": repr(citations)},
        )

    checked_map = _verified(coverage_map, "map_hash", "coverage_map")
    checked_report = _verified(diversity_report, "report_hash", "diversity_report")
    if int(checked_map["generation"]) != int(checked_report["generation"]):
        _fail(
            "MAP_GENERATION_STALE",
            "the coverage map and the diversity report describe different generations",
            {
                "coverage_generation": int(checked_map["generation"]),
                "report_generation": int(checked_report["generation"]),
            },
        )
    sources = {
        str(checked_map["map_id"]): checked_map,
        str(checked_report["report_id"]): checked_report,
    }

    figure_citations: list[Mapping[str, Any]] = []
    authority_citations: list[dict[str, Any]] = []
    for position, candidate_citation in enumerate(citations):
        citation = dict(_require_mapping(candidate_citation, f"citations[{position}]"))
        quotes_figure = "figure" in citation
        names_artifact = "schema" in citation
        if quotes_figure == names_artifact:
            _fail(
                "INPUT_INVALID",
                f"citation {position} must quote a figure or name an artifact schema",
                {"given": citation, "position": position},
            )
        if quotes_figure:
            figure_citations.append(citation)
            continue
        schema = str(citation["schema"])
        if schema not in set(default_registry().names()):
            _fail(
                "CITATION_UNRESOLVED",
                f"citation {position} names schema {schema}, which is not canonical",
                {"position": position, "schema": schema},
            )
        if "artifact_id" not in citation:
            _fail(
                "INPUT_INVALID",
                f"citation {position} names a schema but no artifact",
                {"given": citation, "position": position},
            )
        artifact_id = citation["artifact_id"]
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            _fail(
                "INPUT_INVALID",
                f"citation {position} must name a non-empty artifact id",
                {
                    "artifact_id": artifact_id,
                    "position": position,
                    "value_type": type(artifact_id).__name__,
                },
            )
        if schema in authority_schemas:
            authority_citations.append(
                {"artifact_id": artifact_id, "schema": schema}
            )

    cited_ranking_figures = sorted(
        {
            str(citation["figure"])
            for citation in figure_citations
            if str(citation["figure"]) in RANKING_FIGURE_NAMES
        }
    )
    if not authority_citations:
        _fail(
            "PROMOTION_AUTHORITY_ABSENT",
            f"request {stated['request_id']} names no gate or parliament artifact",
            {
                "authority_schemas": list(authority_schemas),
                "candidate_id": str(stated["candidate_id"]),
                "cited_ranking_figures": cited_ranking_figures,
                "request_id": str(stated["request_id"]),
            },
        )

    informing: list[dict[str, Any]] = []
    for position, citation in enumerate(figure_citations):
        figure = str(citation["figure"])
        source_id = str(citation.get("source_id", ""))
        source = sources.get(source_id)
        if source is None or figure not in source:
            _fail(
                "CITATION_UNRESOLVED",
                f"figure {figure} is not published by any supplied map record",
                {
                    "figure": figure,
                    "known_sources": sorted(sources),
                    "source_id": source_id,
                },
            )
        if "value" not in citation:
            _fail(
                "INPUT_INVALID",
                f"figure citation {position} quotes no value",
                {"figure": figure, "position": position},
            )
        if canonical_json(citation["value"]) != canonical_json(source[figure]):
            _fail(
                "RANKING_FIGURE_FORGED",
                f"the request quotes {figure} as {citation['value']!r}",
                {
                    "figure": figure,
                    "published": source[figure],
                    "quoted": citation["value"],
                    "source_id": source_id,
                },
            )
        informing.append(
            {"figure": figure, "source_id": source_id, "value": source[figure]}
        )

    record: dict[str, Any] = {
        "authority_citations": sorted(
            authority_citations, key=lambda row: canonical_json(row)
        ),
        "candidate_id": str(stated["candidate_id"]),
        "cited_ranking_figures": cited_ranking_figures,
        "counts": {
            "authority_citations": len(authority_citations),
            "informing_figures": len(informing),
        },
        "coverage_map_hash": str(checked_map["map_hash"]),
        "diversity_report_hash": str(checked_report["report_hash"]),
        "generation": int(checked_map["generation"]),
        # Named so a reader can see exactly which figures were allowed to inform
        # the request without being allowed to justify it.
        "informing_figures": sorted(informing, key=lambda row: canonical_json(row)),
        "record_id": record_id or new_id("RSR"),
        "request_id": str(stated["request_id"]),
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record
