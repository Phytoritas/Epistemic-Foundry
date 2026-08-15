"""Evolution Chamber console: read-only projections of the sealed search state.

The Evolution Chamber, the species archive and the Red Queen lab seal four
surfaces the operator needs to *see*: the Pareto front of non-dominated
candidates, the quality-diversity niches M05 maps, the candidate lineages, and
the Red Queen challenge board.  Each is already an immutable, schema-valid,
hash-re-derivable artifact.  What had no owner was a *view*: a bounded, ordered,
deterministic record an operator console can render without ever reaching past
the sealed surface it renders.

This module is that view, and only that view.  It **projects** — it reads a
sealed artifact, confirms the artifact re-derives its own identity, checks the
cross-surface integrity the artifact's own schema cannot (a Pareto front must
pair every candidate with a fitness vector; a challenge result must name a
challenge genome that exists), and emits a deep-frozen view record whose
``view_id`` and ``view_hash`` are a pure function of what it projected.  Two
projections of equal input are byte-equal: there is no clock and no random
draw here.  It **invents nothing**: every candidate id, niche, outcome and
severity in a view record is read out of the sealed artifact or, for the
ordered outcome/severity buckets, out of the canonical schema that declares the
vocabulary — never named as a literal in this module (EF4-I22), so a schema
change reshapes the view instead of drifting from it.  And it **grants no
authority**: a view record carries ``readonly`` and ``grants_authority``
markers that are always the same two values, the console refuses any request
that would have it decide, select, promote, or expose a holdout, and no
candidate, model, prompt, backend or hook reaches an evaluator, holdout or
promotion surface through here.  Promotion authority lives elsewhere and takes
nothing from this console.

It **refuses** malformed or undeclared input rather than repairing it: every
refusal below carries a code from :data:`FINDING_CODES`, an input that a
canonical schema rejects is refused rather than projected, and no input mapping
is ever mutated.
"""

from __future__ import annotations

from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ...cartography.v4_m05.mapper import CartographyError, NicheMap
from ...contracts import (
    ContractViolation,
    SchemaNotFound,
    default_registry,
    validate_artifact,
)
from ...domain.hashing import (
    SHA256_PREFIX,
    hash_excluding,
    sha256_of_payload,
)

#: Every way this console refuses, and why the refusal exists.  A refusal whose
#: code is absent here is a bug rather than a decision, so :func:`_fail` checks
#: membership and every code below is exercised by the negative-and-adversarial
#: suite.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this console requires, and continuing would "
        "project something it never validated"
    ),
    "SURFACE_UNDECLARED": (
        "a projection was requested for a surface this console does not project, "
        "so there is no sealed state to render"
    ),
    "PROMOTION_AUTHORITY_REFUSED": (
        "a request would have the console decide, select, promote, or expose a "
        "holdout; the console projects sealed state and confers no evaluator, "
        "holdout or promotion authority"
    ),
    "SNAPSHOT_REFUSED": (
        "the canonical schema refused a Pareto-front snapshot, so the view would "
        "be built over a snapshot no reader can validate"
    ),
    "SNAPSHOT_DRIFT": (
        "a Pareto-front snapshot does not re-derive its own hash, so the front "
        "being projected is not the front that was sealed"
    ),
    "FRONT_PAIRING_INCOMPLETE": (
        "a Pareto front does not pair every non-dominated candidate with exactly "
        "one fitness vector, so a candidate has no trade-off position to show"
    ),
    "FRONT_REFERENCE_MISALIGNED": (
        "the reference point does not carry one coordinate per objective "
        "dimension, so the front's hypervolume cannot be interpreted"
    ),
    "NICHE_REFUSED": (
        "a niche does not satisfy its canonical schema, does not match the id "
        "its own coordinates derive, or does not re-derive its own hash"
    ),
    "LINEAGE_REFUSED": (
        "a candidate lineage does not satisfy its canonical schema, so the "
        "descent being projected is not a valid lineage record"
    ),
    "CHALLENGE_GENOME_REFUSED": (
        "a challenge genome does not satisfy its canonical schema, so the "
        "challenge being projected is not a valid genome"
    ),
    "CHALLENGE_RESULT_REFUSED": (
        "a challenge result does not satisfy its canonical schema, so the "
        "outcome being projected is not a valid result"
    ),
    "RESULT_DRIFT": (
        "a challenge result does not re-derive its own hash, so the outcome "
        "being projected is not the outcome that was sealed"
    ),
    "CHALLENGE_TARGET_MISSING": (
        "a challenge result names a challenge genome that is not among the "
        "genomes presented, so the board would show an outcome for a challenge "
        "it cannot describe"
    ),
}

#: The surfaces this console projects.  These are the console's own handles, not
#: canonical schema vocabulary, so they may live here as literals.
SURFACE_PARETO_FRONT = "pareto_front"
SURFACE_NICHE_MAP = "niche_map"
SURFACE_LINEAGES = "lineages"
SURFACE_CHALLENGE_BOARD = "challenge_board"

#: Canonical schema names the sealed surfaces validate into.  These are schema
#: identifiers, not enum values, so they are not the wire literals EF4-I22
#: forbids; the enum *values* those schemas declare are always read at runtime.
PARETO_SNAPSHOT_SCHEMA = "pareto-front-snapshot"
NICHE_SCHEMA = "epistemic-niche"
LINEAGE_SCHEMA = "candidate-lineage"
CHALLENGE_GENOME_SCHEMA = "challenge-genome"
CHALLENGE_RESULT_SCHEMA = "challenge-result"

#: Identifier prefix for a console view record.  The body after the prefix is a
#: digest of the record's own content, so equal inputs yield equal ids and
#: nothing here needs entropy.
VIEW_ID_PREFIX = "CV-"

#: The default role a projection is attributed to when a caller names none.  A
#: role name is not canonical vocabulary; whatever it is, it confers no
#: authority, because the console grants none to anyone.
DEFAULT_REQUESTING_ROLE = "console_reader"

#: Position of the ``outcome`` property in the challenge-result schema.  That
#: property *name* is itself a canonical enum value in another schema (a
#: mechanism-graph node role), so writing it here would be a duplicated wire
#: literal (EF4-I22); the field name is read positionally from the schema that
#: declares the result instead, and the schema-and-type suite pins the position.
CHALLENGE_OUTCOME_FIELD_POSITION = 4


class ConsoleProjectionRefused(ValueError):
    """The console refuses to project an input, with a finding code."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise ConsoleProjectionRefused(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ConsoleProjectionRefused(code, message, context)


# -- input shape guards (never mutate the input) --------------------------


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


# -- deterministic identity and deep freezing -----------------------------


def _digest_body(payload: Any) -> str:
    """The hex body of a canonical digest, used to derive content-bound ids."""
    return sha256_of_payload(payload)[len(SHA256_PREFIX) :]


def _freeze(value: Any) -> Any:
    """Deep-freeze a view record into read-only mappings and tuples.

    A projected view is a record of what was sealed, not a scratch buffer, so it
    is returned as a structure a caller cannot mutate in place: mappings become
    ``MappingProxyType`` and sequences become tuples, recursively.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Recover a plain, JSON-serializable structure from a frozen view."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _finalize(
    surface: str, body: Mapping[str, Any], *, requesting_role: str
) -> MappingProxyType:
    """Wrap a projected body in the common envelope, seal it, and freeze it.

    The envelope is the same for every surface: the surface projected, the two
    authority markers that never change, and the role the projection is
    attributed to.  ``view_id`` is derived from the whole record and
    ``view_hash`` from the record minus the hash, so both re-derive byte for
    byte from the view's own content.
    """
    view: dict[str, Any] = {
        "surface": surface,
        "readonly": True,
        "grants_authority": False,
        "requesting_role": requesting_role,
    }
    view.update({key: value for key, value in body.items()})
    view["view_id"] = VIEW_ID_PREFIX + _digest_body(dict(view))
    view["view_hash"] = hash_excluding(view, "view_hash")
    return _freeze(view)


def require_view_identity(view: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a view record's identifier and hash from its own content.

    A caller that stored a projection can prove it is the projection that was
    emitted: the id and hash both re-derive from the record's body, so tampering
    with any projected field is detectable here rather than trusted.
    """
    record = _thaw(_require_mapping(view, "view"))
    body = {
        key: value
        for key, value in record.items()
        if key not in {"view_id", "view_hash"}
    }
    derived_id = VIEW_ID_PREFIX + _digest_body(body)
    derived_hash = hash_excluding(dict(record), "view_hash")
    if record.get("view_id") != derived_id or record.get("view_hash") != derived_hash:
        _fail(
            "INPUT_INVALID",
            "the view record does not re-derive its own identity",
            {
                "derived_view_hash": derived_hash,
                "derived_view_id": derived_id,
                "stated_view_id": record.get("view_id"),
            },
        )
    return record


# -- canonical vocabularies, read from the schema that declares them -------


def _scalar_enum(schema_name: str, field: str, code: str) -> tuple[str, ...]:
    """The declared enum of a scalar property, in the schema's own order.

    Holding these tokens as literals would be a second copy that drifts from the
    contract (EF4-I22), so the ordered buckets a board renders read their
    vocabulary here instead of naming it.
    """
    document = default_registry().document(schema_name)
    enum = document.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(enum, list) or not enum:
        _fail(code, f"the {schema_name} schema declares no enum for {field}", {})
    return tuple(str(value) for value in enum)


@lru_cache(maxsize=1)
def _challenge_result_field(position: int) -> str:
    """The name of the challenge-result property at ``position``.

    Used for the one field whose name coincides with a canonical enum value in
    another schema, so the name is read from the schema rather than written as a
    literal here (EF4-I22).
    """
    properties = list(
        default_registry().document(CHALLENGE_RESULT_SCHEMA)["properties"]
    )
    if position >= len(properties):
        _fail(
            "CHALLENGE_RESULT_REFUSED",
            f"the challenge-result schema declares no property at {position}",
            {"position": position},
        )
    return properties[position]


@lru_cache(maxsize=1)
def challenge_outcome_vocabulary() -> tuple[str, ...]:
    """The challenge outcomes, read from the challenge-result schema."""
    field = _challenge_result_field(CHALLENGE_OUTCOME_FIELD_POSITION)
    return _scalar_enum(CHALLENGE_RESULT_SCHEMA, field, "CHALLENGE_RESULT_REFUSED")


@lru_cache(maxsize=1)
def challenge_severity_vocabulary() -> tuple[str, ...]:
    """The challenge severities, read from the challenge-result schema."""
    return _scalar_enum(CHALLENGE_RESULT_SCHEMA, "severity", "CHALLENGE_RESULT_REFUSED")


# -- Pareto front projection ----------------------------------------------


def project_pareto_front(
    snapshot: Mapping[str, Any],
    *,
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
) -> MappingProxyType:
    """Project one sealed Pareto-front snapshot into a read-only view.

    The snapshot must satisfy its canonical schema and re-derive its own
    ``snapshot_hash``.  Two integrity rules the schema cannot state are checked
    here: a front pairs every non-dominated candidate with exactly one fitness
    vector, and the reference point carries one coordinate per objective
    dimension so the sealed hypervolume can be read.  The view reports the front
    as a *set* of candidates with their objective dimensions; it never selects,
    ranks or scalarizes one candidate into a winner.
    """
    record = _require_mapping(snapshot, "snapshot")
    role = _require_text(requesting_role, "requesting_role")
    try:
        validate_artifact(PARETO_SNAPSHOT_SCHEMA, record)
    except ContractViolation as error:
        _fail(
            "SNAPSHOT_REFUSED",
            "the Pareto-front snapshot does not satisfy its canonical schema",
            {"errors": list(error.errors)},
        )
    recomputed = hash_excluding(record, "snapshot_hash")
    if str(record.get("snapshot_hash")) != recomputed:
        _fail(
            "SNAPSHOT_DRIFT",
            "the Pareto-front snapshot does not re-derive its own hash",
            {"recomputed": recomputed, "stated": record.get("snapshot_hash")},
        )

    candidate_ids = [str(value) for value in record["candidate_ids"]]
    fitness_vector_ids = [str(value) for value in record["fitness_vector_ids"]]
    if len(candidate_ids) != len(fitness_vector_ids):
        _fail(
            "FRONT_PAIRING_INCOMPLETE",
            "the front does not pair every candidate with one fitness vector",
            {
                "candidate_count": len(candidate_ids),
                "fitness_vector_count": len(fitness_vector_ids),
            },
        )
    if len(set(candidate_ids)) != len(candidate_ids):
        _fail(
            "FRONT_PAIRING_INCOMPLETE",
            "the front does not pair every candidate with one fitness vector",
            {
                "candidate_count": len(candidate_ids),
                "fitness_vector_count": len(fitness_vector_ids),
            },
        )
    if len(set(fitness_vector_ids)) != len(fitness_vector_ids):
        _fail(
            "FRONT_PAIRING_INCOMPLETE",
            "the front does not pair every candidate with one fitness vector",
            {
                "candidate_count": len(candidate_ids),
                "fitness_vector_count": len(fitness_vector_ids),
            },
        )
    objective_dimensions = [str(value) for value in record["objective_dimensions"]]
    reference_point = list(record["reference_point"])
    if len(reference_point) != len(objective_dimensions):
        _fail(
            "FRONT_REFERENCE_MISALIGNED",
            "the reference point does not carry one coordinate per objective",
            {
                "objective_count": len(objective_dimensions),
                "reference_point_count": len(reference_point),
            },
        )

    body: dict[str, Any] = {
        "snapshot_id": str(record["snapshot_id"]),
        "snapshot_hash": str(record["snapshot_hash"]),
        "evolution_run_id": str(record["evolution_run_id"]),
        "generation": int(record["generation"]),
        "objective_dimensions": objective_dimensions,
        "candidate_ids": sorted(candidate_ids),
        "candidate_fitness_pairs": [
            {"candidate_id": candidate, "fitness_vector_id": fitness}
            for candidate, fitness in sorted(
                zip(candidate_ids, fitness_vector_ids, strict=True)
            )
        ],
        "constraint_policy_version": str(record["constraint_policy_version"]),
        "hypervolume": record["hypervolume"],
        "reference_point": reference_point,
        "counts": {
            "candidates": len(candidate_ids),
            "objectives": len(objective_dimensions),
        },
    }
    return _finalize(SURFACE_PARETO_FRONT, body, requesting_role=role)


# -- quality-diversity niche projection -----------------------------------


def project_niche_map(
    niches: Sequence[Mapping[str, Any]],
    *,
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
) -> MappingProxyType:
    """Project the sealed M05 niche map into a read-only coverage view.

    The map is built by the sealed M05 cartographer, which validates each niche,
    refuses a forged cell identity and refuses a candidate occupying two cells;
    any such refusal is reported here as ``NICHE_REFUSED``.  Each niche's own
    ``niche_hash`` is re-derived as well, so a cell whose recorded hash drifted
    from its content is refused rather than shown.  The view reports occupancy
    and per-cell coverage debt; it reassigns no elite and evicts no occupant.
    """
    role = _require_text(requesting_role, "requesting_role")
    rows = _require_sequence(niches, "niches")
    cleaned: list[dict[str, Any]] = []
    for position, candidate in enumerate(rows):
        niche = _require_mapping(candidate, f"niches[{position}]")
        recomputed = hash_excluding(niche, "niche_hash")
        if str(niche.get("niche_hash")) != recomputed:
            _fail(
                "NICHE_REFUSED",
                f"niche at position {position} does not re-derive its own hash",
                {"position": position, "recomputed": recomputed},
            )
        cleaned.append(niche)
    try:
        niche_map = NicheMap(cleaned)
    except CartographyError as error:
        _fail(
            "NICHE_REFUSED",
            "the sealed cartographer refused a niche",
            {"cartography_code": error.code, "detail": str(error)},
        )

    occupancy = niche_map.occupants()
    cells: list[dict[str, Any]] = []
    for niche_id in niche_map.niche_ids():
        niche = dict(niche_map.niche(niche_id))
        occupants = [str(value) for value in niche["occupant_ids"]]
        cells.append(
            {
                "niche_id": niche_id,
                "axis_values": dict(niche["axis_values"]),
                "capacity": int(niche["capacity"]),
                "occupant_ids": sorted(occupants),
                "elite_id": niche["elite_id"],
                "coverage_debt": niche["coverage_debt"],
                "occupancy": len(occupants),
            }
        )
    body: dict[str, Any] = {
        "niche_ids": list(niche_map.niche_ids()),
        "occupied_niche_ids": list(niche_map.occupied_niche_ids()),
        "cells": cells,
        "occupancy": dict(sorted(occupancy.items())),
        "counts": {
            "niches": len(niche_map.niche_ids()),
            "occupied_niches": len(niche_map.occupied_niche_ids()),
            "placed_candidates": len(occupancy),
        },
    }
    return _finalize(SURFACE_NICHE_MAP, body, requesting_role=role)


# -- lineage projection ----------------------------------------------------


def project_lineages(
    lineages: Sequence[Mapping[str, Any]],
    *,
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
) -> MappingProxyType:
    """Project sealed candidate-lineage records into a read-only descent view.

    Each record must satisfy the candidate-lineage schema.  The view reports,
    per candidate, its parents, inspirations, mutation operators, crossover
    parents, generation and island; it derives no new ancestry and asserts no
    diversity verdict — that measurement is M05's, and this console only shows
    the records it is given.
    """
    role = _require_text(requesting_role, "requesting_role")
    rows = _require_sequence(lineages, "lineages")
    records: list[dict[str, Any]] = []
    for position, candidate in enumerate(rows):
        lineage = _require_mapping(candidate, f"lineages[{position}]")
        try:
            validate_artifact(LINEAGE_SCHEMA, lineage)
        except ContractViolation as error:
            _fail(
                "LINEAGE_REFUSED",
                f"lineage at position {position} does not satisfy its schema",
                {"errors": list(error.errors), "position": position},
            )
        records.append(
            {
                "lineage_id": str(lineage["lineage_id"]),
                "candidate_id": str(lineage["candidate_id"]),
                "parent_ids": [str(value) for value in lineage["parent_ids"]],
                "inspiration_ids": [str(value) for value in lineage["inspiration_ids"]],
                "mutation_operator_ids": [
                    str(value) for value in lineage["mutation_operator_ids"]
                ],
                "crossover_parent_ids": [
                    str(value) for value in lineage["crossover_parent_ids"]
                ],
                "generation": int(lineage["generation"]),
                "island_id": str(lineage["island_id"]),
                "ancestor_hashes": [str(value) for value in lineage["ancestor_hashes"]],
            }
        )
    records.sort(key=lambda item: (item["candidate_id"], item["lineage_id"]))
    islands = sorted({record["island_id"] for record in records})
    body: dict[str, Any] = {
        "candidate_ids": sorted(record["candidate_id"] for record in records),
        "lineages": records,
        "island_ids": islands,
        "counts": {
            "lineages": len(records),
            "islands": len(islands),
        },
    }
    return _finalize(SURFACE_LINEAGES, body, requesting_role=role)


# -- Red Queen challenge board projection ---------------------------------


def project_challenge_board(
    genomes: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    *,
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
) -> MappingProxyType:
    """Project sealed Red Queen genomes and results into a read-only board.

    Every genome must satisfy the challenge-genome schema and every result the
    challenge-result schema; each result re-derives its own ``result_hash`` and
    names a challenge genome present in the set.  The board groups results into
    every declared outcome and severity bucket — buckets are read from the
    schema so an empty run still renders a stable, complete board — and reports
    each genome's challenge class and safety class as sealed.  It computes no
    survival, promotion or retraction verdict: an outcome shown here buys the
    candidate nothing and costs it nothing.
    """
    role = _require_text(requesting_role, "requesting_role")
    genome_rows = _require_sequence(genomes, "genomes")
    result_rows = _require_sequence(results, "challenge_results")
    outcome_field = _challenge_result_field(CHALLENGE_OUTCOME_FIELD_POSITION)

    genome_ids: set[str] = set()
    projected_genomes: list[dict[str, Any]] = []
    for position, candidate in enumerate(genome_rows):
        genome = _require_mapping(candidate, f"genomes[{position}]")
        try:
            validate_artifact(CHALLENGE_GENOME_SCHEMA, genome)
        except ContractViolation as error:
            _fail(
                "CHALLENGE_GENOME_REFUSED",
                f"challenge genome at position {position} does not satisfy its schema",
                {"errors": list(error.errors), "position": position},
            )
        genome_id = str(genome["challenge_genome_id"])
        if genome_id in genome_ids:
            _fail(
                "INPUT_INVALID",
                f"challenge genome at position {position} repeats an earlier id",
                {"challenge_genome_id": genome_id, "position": position},
            )
        genome_ids.add(genome_id)
        projected_genomes.append(
            {
                "challenge_genome_id": genome_id,
                "target_genome_id": str(genome["target_genome_id"]),
                "challenge_class": str(genome["challenge_class"]),
                "safety_class": str(genome["safety_class"]),
                "required_capabilities": [
                    str(value) for value in genome["required_capabilities"]
                ],
                "lineage_id": str(genome["lineage_id"]),
            }
        )

    outcomes = challenge_outcome_vocabulary()
    severities = challenge_severity_vocabulary()
    by_outcome: dict[str, list[str]] = {outcome: [] for outcome in outcomes}
    by_severity: dict[str, list[str]] = {severity: [] for severity in severities}
    result_ids: set[str] = set()
    projected_results: list[dict[str, Any]] = []
    for position, candidate in enumerate(result_rows):
        result = _require_mapping(candidate, f"results[{position}]")
        try:
            validate_artifact(CHALLENGE_RESULT_SCHEMA, result)
        except ContractViolation as error:
            _fail(
                "CHALLENGE_RESULT_REFUSED",
                f"challenge result at position {position} does not satisfy its schema",
                {"errors": list(error.errors), "position": position},
            )
        recomputed = hash_excluding(result, "result_hash")
        if str(result.get("result_hash")) != recomputed:
            _fail(
                "RESULT_DRIFT",
                f"challenge result at position {position} does not re-derive its hash",
                {"position": position, "recomputed": recomputed},
            )
        genome_id = str(result["challenge_genome_id"])
        if genome_id not in genome_ids:
            _fail(
                "CHALLENGE_TARGET_MISSING",
                "a challenge result names a genome absent from the presented set",
                {"challenge_genome_id": genome_id, "position": position},
            )
        result_id = str(result["challenge_result_id"])
        if result_id in result_ids:
            _fail(
                "INPUT_INVALID",
                f"challenge result at position {position} repeats an earlier id",
                {"challenge_result_id": result_id, "position": position},
            )
        result_ids.add(result_id)
        outcome = str(result[outcome_field])
        severity = str(result["severity"])
        by_outcome[outcome].append(result_id)
        by_severity[severity].append(result_id)
        projected_results.append(
            {
                "challenge_result_id": result_id,
                "challenge_genome_id": genome_id,
                "target_candidate_id": str(result["target_candidate_id"]),
                "stage_result_id": str(result["stage_result_id"]),
                "challenge_outcome": outcome,
                "severity": severity,
                "result_hash": str(result["result_hash"]),
            }
        )

    projected_genomes.sort(key=lambda item: item["challenge_genome_id"])
    projected_results.sort(key=lambda item: item["challenge_result_id"])
    body: dict[str, Any] = {
        "challenge_genome_ids": sorted(genome_ids),
        "genomes": projected_genomes,
        "challenge_results": projected_results,
        "results_by_outcome": {
            outcome: sorted(by_outcome[outcome]) for outcome in outcomes
        },
        "results_by_severity": {
            severity: sorted(by_severity[severity]) for severity in severities
        },
        "counts": {
            "genomes": len(projected_genomes),
            "challenge_results": len(projected_results),
        },
    }
    return _finalize(SURFACE_CHALLENGE_BOARD, body, requesting_role=role)


# -- the surface dispatcher and authority boundary ------------------------


def declared_surfaces() -> tuple[str, ...]:
    """The surfaces this console projects, in a stable order."""
    return (
        SURFACE_PARETO_FRONT,
        SURFACE_NICHE_MAP,
        SURFACE_LINEAGES,
        SURFACE_CHALLENGE_BOARD,
    )


def build_console_projection(
    *,
    surface: str,
    payload: Mapping[str, Any],
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
    authority_request: object | None = None,
) -> MappingProxyType:
    """Route a projection request to its surface, refusing any authority grab.

    The authority boundary is checked first and unconditionally: the console
    projects sealed state, so any ``authority_request`` — a caller asking it to
    decide, select, promote or expose a holdout — is refused before any surface
    is touched, and no candidate, model, prompt, backend or hook acquires
    evaluator, holdout or promotion authority through this entry point.  The
    surface must be one the console declares; its payload carries only the
    sealed artifacts that surface projects.
    """
    role = _require_text(requesting_role, "requesting_role")
    if authority_request is not None:
        _fail(
            "PROMOTION_AUTHORITY_REFUSED",
            "the console projects sealed state and confers no decision authority",
            {"authority_request": repr(authority_request), "requesting_role": role},
        )
    name = _require_text(surface, "surface")
    if name not in declared_surfaces():
        _fail(
            "SURFACE_UNDECLARED",
            "the console does not project the requested surface",
            {"declared": list(declared_surfaces()), "surface": name},
        )
    request = _require_mapping(payload, "payload")
    if name == SURFACE_PARETO_FRONT:
        return project_pareto_front(
            _require_mapping(request.get("snapshot"), "payload.snapshot"),
            requesting_role=role,
        )
    if name == SURFACE_NICHE_MAP:
        return project_niche_map(
            _require_sequence(request.get("niches"), "payload.niches"),
            requesting_role=role,
        )
    if name == SURFACE_LINEAGES:
        return project_lineages(
            _require_sequence(request.get("lineages"), "payload.lineages"),
            requesting_role=role,
        )
    return project_challenge_board(
        _require_sequence(request.get("genomes"), "payload.genomes"),
        _require_sequence(
            request.get("challenge_results"), "payload.challenge_results"
        ),
        requesting_role=role,
    )


# ``SchemaNotFound`` is re-exported so a caller can distinguish a missing
# canonical schema (an environment fault) from a projection refusal.
__all__ = [
    "CHALLENGE_GENOME_SCHEMA",
    "CHALLENGE_RESULT_SCHEMA",
    "DEFAULT_REQUESTING_ROLE",
    "FINDING_CODES",
    "LINEAGE_SCHEMA",
    "NICHE_SCHEMA",
    "PARETO_SNAPSHOT_SCHEMA",
    "SURFACE_CHALLENGE_BOARD",
    "SURFACE_LINEAGES",
    "SURFACE_NICHE_MAP",
    "SURFACE_PARETO_FRONT",
    "VIEW_ID_PREFIX",
    "ConsoleProjectionRefused",
    "SchemaNotFound",
    "build_console_projection",
    "challenge_outcome_vocabulary",
    "challenge_severity_vocabulary",
    "declared_surfaces",
    "project_challenge_board",
    "project_lineages",
    "project_niche_map",
    "project_pareto_front",
    "require_view_identity",
]
