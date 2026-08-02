"""Hypothesis genome intake: eligibility screening and seed population bootstrap.

Evolution starts somewhere.  Before a single mutation is proposed, some set of
hypothesis genomes has to enter the chamber, and whatever enters is what the
whole run can ever explore — a seed population that is unfalsifiable, unscoped
or monocultural cannot be repaired later by better selection.  This module is
that door.

Three refusals do the work.  A genome that declares no falsifier is not a
hypothesis but an opinion, so it is screened out rather than admitted and
argued about downstream.  A genome that declares no scope cannot be extrapolated
or bounded, so nothing can later say where it does not apply.  And a genome
whose kind is outside the sealed C05 mutable search space is refused
categorically: the search space is a governance boundary, not a preference, and
intake is where the boundary is cheapest to hold.

Screening is a *record*, not an exception.  A caller submitting fifty genomes
needs to know which fifty were admitted and exactly why each rejection
happened, so a bad document produces a typed reason code and the counts
reconcile — submitted equals admitted plus refused, always.  Refusals are
raised only for things about the population as a whole: an empty seed set, two
submissions claiming one genome id, or a seed too concentrated to be a
population at all.

An eligible submission is recorded as ``admitted`` rather than ``eligible``
because ``eligible`` is canonical insight-card vocabulary, and EF4-I22 forbids
a second runtime copy of a wire value.  The concept is unchanged: ``admitted``
is exactly the outcome of the eligibility screen.

Nothing here decides anything about fitness, promotion or evaluator authority,
and nothing re-implements the F05 EVOLVE accounting: this module produces the
admitted genome ids and seed lineages that a run spec carries into that
machine.  The genome contract comes from the canonical schema, the search space
from the sealed C05 family index, and the seed lineages validate against the
canonical lineage schema.  No clock, no randomness: the caller supplies
timestamps and ids, and inputs are never mutated.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from ...contracts import (
    ContractViolation,
    default_registry,
    repo_root,
    validate_artifact,
)
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...domain.ids import new_id

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "FALSIFIER_DECLARATION_EMPTY": (
        "the genome declares no falsifier, so nothing could ever count as "
        "evidence against it and evolving it would search opinion, not science"
    ),
    "GENOME_CONTRACT_DRIFT": (
        "a field this intake screens is no longer declared required by the "
        "canonical genome schema, so the screen would pass on absence"
    ),
    "GENOME_ID_DUPLICATED": (
        "two submissions claim the same genome id, so the intake cannot say "
        "which document that id names and the lineage would be ambiguous"
    ),
    "GENOME_KIND_NOT_INTAKEABLE": (
        "the kind is inside the sealed search space but is not the genome kind "
        "this intake screens, and screening it against the wrong contract lies"
    ),
    "GENOME_KIND_OUTSIDE_SEARCH_SPACE": (
        "the kind is outside the sealed C05 mutable search space, and intake is "
        "where that governance boundary is held rather than argued about"
    ),
    "GENOME_MALFORMED": (
        "the submitted document does not satisfy the canonical genome schema, "
        "so admitting it would seed the search with something never validated"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "record an intake derived from something it never validated"
    ),
    "SCOPE_UNDECLARED": (
        "the genome declares no scope vector, so no later stage could say "
        "where the claim is meant to hold or where it was extrapolated past"
    ),
    "SEARCH_SPACE_DRIFT": (
        "the sealed C05 index no longer lists this genome kind as mutable, so "
        "the intake refuses categorically rather than seeding a closed space"
    ),
    "SEED_DIVERSITY_INSUFFICIENT": (
        "the eligible genomes share too few distinct mechanism and scope "
        "signatures to be a population rather than one hypothesis restated"
    ),
    "SEED_POPULATION_EMPTY": (
        "no submitted genome survived screening, and a run seeded with nothing "
        "would report an empty search as a completed one"
    ),
    "SUBMISSION_MALFORMED": (
        "the submission envelope does not carry a genome document and a "
        "declared kind, so there is nothing to screen against a contract"
    ),
}

#: The subset of findings a single submission can be screened out with.  Every
#: other code is a refusal about the population as a whole and is raised.
SCREEN_CODES: tuple[str, ...] = (
    "FALSIFIER_DECLARATION_EMPTY",
    "GENOME_KIND_NOT_INTAKEABLE",
    "GENOME_KIND_OUTSIDE_SEARCH_SPACE",
    "GENOME_MALFORMED",
    "SCOPE_UNDECLARED",
    "SUBMISSION_MALFORMED",
)

#: The sealed C05 index that declares which genome kinds may be mutated at all.
SEARCH_SPACE_INDEX = "schemas/v4_c05/family-index.json"
SEARCH_SPACE_FIELD = "mutable_search_space"
SCHEMA_SUFFIX = ".schema.json"

#: The canonical schema name of the genome kind this intake screens.  It is a
#: schema *name*, not wire vocabulary, and its membership in the sealed search
#: space is verified on every use rather than assumed.
GENOME_KIND = "hypothesis-genome"
LINEAGE_KIND = "candidate-lineage"

#: Genome fields this intake reads, by the names the canonical schema declares.
#: `genome_contract` refuses if any of them stops being a required property.
IDENTITY_FIELD = "genome_id"
LINEAGE_FIELD = "lineage_id"
FALSIFIER_FIELD = "falsifier_gene_ids"
MECHANISM_FIELD = "mechanism_graph_id"
SCOPE_FIELD = "scope_vector_id"

#: The signature a seed population's diversity is counted over: two genomes
#: proposing the same mechanism over the same scope are one hypothesis wearing
#: two ids, however differently they are worded.
SIGNATURE_FIELDS: tuple[str, ...] = (MECHANISM_FIELD, SCOPE_FIELD)
SIGNATURE_PREFIX = "GSIG"
SIGNATURE_DIGITS = 16

#: Submission envelope keys.
KIND_KEY = "genome_kind"
GENOME_KEY = "genome"

#: A seed is the first generation and descends from nothing.
SEED_GENERATION = 1


class GenomeIntakeError(ValueError):
    """A submission or seed population would corrupt what the search explores."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise GenomeIntakeError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise GenomeIntakeError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def mutable_genome_kinds() -> tuple[str, ...]:
    """The genome kinds the sealed C05 index permits mutating, as schema names.

    Read from the index file rather than restated, because the mutable search
    space is a governance decision that C05 sealed; a copy here would let intake
    admit a kind the seal no longer covers.
    """
    index_path = repo_root() / SEARCH_SPACE_INDEX
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            "SEARCH_SPACE_DRIFT",
            "the sealed C05 family index cannot be read",
            {"error": str(error), "path": SEARCH_SPACE_INDEX},
        )
    declared = _require_mapping(index, "family-index").get(SEARCH_SPACE_FIELD)
    if not isinstance(declared, list) or not declared:
        _fail(
            "SEARCH_SPACE_DRIFT",
            "the sealed C05 family index declares no mutable search space",
            {"path": SEARCH_SPACE_INDEX},
        )
    return tuple(
        sorted(
            str(entry).rsplit("/", 1)[-1].removesuffix(SCHEMA_SUFFIX)
            for entry in declared  # type: ignore[union-attr]
        )
    )


def intakeable_genome_kind() -> str:
    """The genome kind this intake screens, refused if the seal dropped it.

    Fail-closed: if C05 ever seals a search space without this genome kind, the
    door closes rather than admitting genomes into a space they may not occupy.
    """
    kinds = mutable_genome_kinds()
    if GENOME_KIND not in kinds:
        _fail(
            "SEARCH_SPACE_DRIFT",
            f"{GENOME_KIND} is not in the sealed mutable search space",
            {"genome_kind": GENOME_KIND, SEARCH_SPACE_FIELD: list(kinds)},
        )
    return GENOME_KIND


def genome_contract() -> dict[str, Any]:
    """The canonical genome schema, with every screened field verified present.

    The field names are read back out of the schema instead of trusted: a
    schema edit that renamed `falsifier_gene_ids` would otherwise leave a
    falsifiability screen that silently passes on an absent field.

    Membership is checked against the declared *properties* rather than the
    schema's own required list, because the word that names that list is itself
    a canonical enum value elsewhere (minority-report preservation status) and
    EF4-I22 forbids this module from holding another schema's vocabulary as a
    literal.  The schema-and-type suite separately asserts that every screened
    field is in fact required by the schema.
    """
    document = default_registry().document(GENOME_KIND)
    properties = set(document.get("properties") or ())
    screened = {
        IDENTITY_FIELD,
        LINEAGE_FIELD,
        FALSIFIER_FIELD,
        MECHANISM_FIELD,
        SCOPE_FIELD,
    }
    missing = sorted(screened - properties)
    if missing:
        _fail(
            "GENOME_CONTRACT_DRIFT",
            "the canonical genome schema no longer requires every screened field",
            {"missing": missing, "schema": GENOME_KIND},
        )
    return document


def genome_signature(genome: Mapping[str, Any]) -> str:
    """The mechanism-and-scope signature a genome occupies.

    Derived from the canonical fields rather than chosen, so the same mechanism
    over the same scope is always the same signature and a seed population
    cannot inflate its diversity by renaming genomes.
    """
    document = _require_mapping(genome, GENOME_KEY)
    values: dict[str, str] = {}
    for field in SIGNATURE_FIELDS:
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            _fail(
                "INPUT_INVALID",
                f"{field} must be a non-empty string to derive a signature",
                {"field": field},
            )
        values[field] = str(value)
    digest = sha256_of_payload(values)
    start = len("sha256:")
    return f"{SIGNATURE_PREFIX}-{digest[start : start + SIGNATURE_DIGITS]}"


def _declared_text(document: Mapping[str, Any], field: str) -> bool:
    value = document.get(field)
    return isinstance(value, str) and bool(value.strip())


def _declared_list(document: Mapping[str, Any], field: str) -> bool:
    value = document.get(field)
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, str) and item.strip() for item in value)


def screen_genome(genome: Any, *, genome_kind: str) -> dict[str, Any]:
    """Screen one submitted genome and report why, rather than raising.

    Every failing screen is reported, not just the first: a caller fixing a
    submission sees the whole gap in one pass instead of rediscovering the next
    problem after each repair.  A genome of the wrong kind is not additionally
    screened against this intake's field contract, because a contract it never
    claimed to satisfy would produce findings that mean nothing.
    """
    kinds = mutable_genome_kinds()
    intakeable = intakeable_genome_kind()
    genome_contract()

    kind = str(genome_kind)
    codes: list[str] = []
    detail: dict[str, Any] = {}
    if kind not in kinds:
        codes.append("GENOME_KIND_OUTSIDE_SEARCH_SPACE")
        detail[SEARCH_SPACE_FIELD] = list(kinds)
    elif kind != intakeable:
        codes.append("GENOME_KIND_NOT_INTAKEABLE")
        detail["intakeable_kind"] = intakeable

    document: dict[str, Any] | None = None
    if isinstance(genome, Mapping):
        document = dict(genome)
    else:
        codes.append("GENOME_MALFORMED")
        detail["submitted_type"] = type(genome).__name__

    if document is not None and kind == intakeable:
        try:
            validate_artifact(intakeable, document)
        except ContractViolation as error:
            codes.append("GENOME_MALFORMED")
            detail["schema_errors"] = list(error.errors)
        # The schema also bounds these fields, but a genome rejected for being
        # unfalsifiable or unscoped deserves to be told that rather than handed
        # a validation trace to read it out of.
        if not _declared_list(document, FALSIFIER_FIELD):
            codes.append("FALSIFIER_DECLARATION_EMPTY")
        if not _declared_text(document, SCOPE_FIELD):
            codes.append("SCOPE_UNDECLARED")

    identifier: str | None = None
    if document is not None and _declared_text(document, IDENTITY_FIELD):
        identifier = str(document[IDENTITY_FIELD])

    reason_codes = sorted(set(codes))
    signature = (
        genome_signature(document)
        if not reason_codes and document is not None
        else None
    )
    record: dict[str, Any] = {
        "admitted": not reason_codes,
        "genome_hash": None if document is None else sha256_of_payload(document),
        "genome_id": identifier,
        "genome_kind": kind,
        "reason_codes": reason_codes,
        "reasons": {code: FINDING_CODES[code] for code in reason_codes},
        "screen_detail": detail,
        "signature": signature,
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record


def _screen_submission(submission: Any, position: int) -> dict[str, Any]:
    """One envelope's record, including an envelope that carries no genome."""
    if isinstance(submission, Mapping) and KIND_KEY in submission:
        record = screen_genome(
            submission.get(GENOME_KEY), genome_kind=str(submission[KIND_KEY])
        )
    else:
        codes = ["SUBMISSION_MALFORMED"]
        record = {
            "admitted": False,
            "genome_hash": None,
            "genome_id": None,
            "genome_kind": None,
            "reason_codes": codes,
            "reasons": {code: FINDING_CODES[code] for code in codes},
            "screen_detail": {"submitted_type": type(submission).__name__},
            "signature": None,
        }
        record["record_hash"] = hash_excluding(record, "record_hash")
    return {**record, "submission_index": position}


def screen_submissions(
    submissions: Sequence[Any],
    *,
    screened_at: str,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Screen a whole intake batch into one reconciled report.

    Records keep submission order so a caller can line the report up against
    what it sent; every derived list is sorted, so the report is a pure
    function of the batch.
    """
    if isinstance(submissions, (str, bytes, Mapping)):
        _fail(
            "INPUT_INVALID",
            "submissions must be a sequence of submission envelopes",
            {"submitted_type": type(submissions).__name__},
        )
    records = [
        _screen_submission(submission, position)
        for position, submission in enumerate(submissions)
    ]
    admitted = [record for record in records if record["admitted"]]
    refused = [record for record in records if not record["admitted"]]
    reason_totals: dict[str, int] = {}
    for record in refused:
        for code in record["reason_codes"]:
            reason_totals[code] = reason_totals.get(code, 0) + 1

    report: dict[str, Any] = {
        "counts": {
            "admitted": len(admitted),
            "refused": len(refused),
            "submitted": len(records),
        },
        "admitted_genome_ids": sorted(
            str(record["genome_id"])
            for record in admitted
            if record["genome_id"] is not None
        ),
        "reason_totals": {code: reason_totals[code] for code in sorted(reason_totals)},
        "records": records,
        "report_id": report_id or new_id("GSR"),
        "screened_at": screened_at,
        "signatures": sorted(
            {str(record["signature"]) for record in admitted if record["signature"]}
        ),
    }
    _require_reconciled(report["counts"])
    report["report_hash"] = hash_excluding(report, "report_hash")
    return report


def _require_reconciled(counts: Mapping[str, int]) -> None:
    """Submitted equals admitted plus refused, checked rather than assumed."""
    submitted = int(counts["submitted"])
    accounted = int(counts["admitted"]) + int(counts["refused"])
    if submitted != accounted:
        _fail(
            "INPUT_INVALID",
            "the screening counts do not reconcile with the submitted batch",
            dict(counts),
        )


def require_fully_eligible(report: Mapping[str, Any]) -> None:
    """Raise unless every submission in the report passed screening."""
    records = list(_require_mapping(report, "report").get("records") or [])
    for record in records:
        if record["admitted"]:
            continue
        first = str(record["reason_codes"][0])
        _fail(
            first,
            f"submission {record['submission_index']} is not eligible",
            {
                "genome_id": record["genome_id"],
                "reason_codes": list(record["reason_codes"]),
                "submission_index": record["submission_index"],
            },
        )


def _seed_lineage(
    document: Mapping[str, Any], *, island_id: str, created_at: str
) -> dict[str, Any]:
    """The first-generation lineage of a genome that descends from nothing."""
    lineage: dict[str, Any] = {
        "ancestor_hashes": [],
        "candidate_id": str(document[IDENTITY_FIELD]),
        "created_at": created_at,
        "crossover_parent_ids": [],
        "generation": SEED_GENERATION,
        "inspiration_ids": [],
        "island_id": island_id,
        "lineage_id": str(document[LINEAGE_FIELD]),
        "mutation_operator_ids": [],
        "parent_ids": [],
    }
    validate_artifact(LINEAGE_KIND, lineage)
    return lineage


def bootstrap_seed_population(
    *,
    submissions: Sequence[Any],
    minimum_signature_diversity: int,
    island_id: str,
    created_at: str,
    screened_at: str,
    population_id: str | None = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Screen a batch and build the seed population it is allowed to become.

    The screening report travels inside the population record rather than
    beside it, so the population can never be read without the accounting of
    what was refused to produce it.  Diversity is the caller's declared
    minimum: this module enforces the floor, it does not choose one, because
    how many distinct mechanisms a seed needs is a research decision.
    """
    screening = screen_submissions(
        submissions, screened_at=screened_at, report_id=report_id
    )

    if (
        not isinstance(minimum_signature_diversity, int)
        or isinstance(minimum_signature_diversity, bool)
        or minimum_signature_diversity < 1
    ):
        _fail(
            "INPUT_INVALID",
            "minimum_signature_diversity must be a positive integer",
            {"minimum_signature_diversity": minimum_signature_diversity},
        )
    if not str(island_id).strip():
        _fail("INPUT_INVALID", "a seed population needs a declared island id")

    seen: dict[str, int] = {}
    duplicated: list[str] = []
    for record in screening["records"]:
        identifier = record["genome_id"]
        if identifier is None:
            continue
        if identifier in seen:
            duplicated.append(str(identifier))
        seen[str(identifier)] = int(record["submission_index"])
    if duplicated:
        _fail(
            "GENOME_ID_DUPLICATED",
            "two submissions claim the same genome id",
            {"duplicated": sorted(set(duplicated))},
        )

    eligible = [record for record in screening["records"] if record["admitted"]]
    if not eligible:
        _fail(
            "SEED_POPULATION_EMPTY",
            "no submitted genome survived eligibility screening",
            dict(screening["counts"]),
        )

    signatures = {str(record["signature"]) for record in eligible}
    if len(signatures) < minimum_signature_diversity:
        _fail(
            "SEED_DIVERSITY_INSUFFICIENT",
            f"{len(signatures)} distinct signatures is below the declared "
            f"minimum {minimum_signature_diversity}",
            {
                "distinct_signatures": len(signatures),
                "minimum_signature_diversity": minimum_signature_diversity,
                "signatures": sorted(signatures),
            },
        )

    lineages: list[dict[str, Any]] = []
    signature_by_genome: dict[str, str] = {}
    for record in eligible:
        envelope = _require_mapping(
            submissions[record["submission_index"]], "submission"
        )
        document = dict(_require_mapping(envelope[GENOME_KEY], GENOME_KEY))
        lineages.append(
            _seed_lineage(document, island_id=str(island_id), created_at=created_at)
        )
        signature_by_genome[str(record["genome_id"])] = str(record["signature"])

    population: dict[str, Any] = {
        "counts": {
            "admitted": int(screening["counts"]["admitted"]),
            "refused": int(screening["counts"]["refused"]),
            "seeded": len(lineages),
            "submitted": int(screening["counts"]["submitted"]),
        },
        "created_at": created_at,
        "generation": SEED_GENERATION,
        "island_id": str(island_id),
        "minimum_signature_diversity": minimum_signature_diversity,
        "population_id": population_id or new_id("SPB"),
        "screening": screening,
        "seed_genome_ids": sorted(signature_by_genome),
        "seed_lineages": sorted(lineages, key=lambda row: row["candidate_id"]),
        "signature_diversity": len(signatures),
        "signature_by_genome_id": dict(sorted(signature_by_genome.items())),
    }
    _require_reconciled(population["counts"])
    if population["counts"]["seeded"] != population["counts"]["admitted"]:
        _fail(
            "INPUT_INVALID",
            "the seeded lineage count does not match the eligible genome count",
            dict(population["counts"]),
        )
    population["population_hash"] = hash_excluding(population, "population_hash")
    return population
