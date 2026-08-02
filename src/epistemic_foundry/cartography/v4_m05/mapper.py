"""Evolution cartography: niche identity, lineage diversity, blast radius.

The archive stores entries and the store persists them, but three questions
about the *shape* of the search had no owner.  Which cell of the semantic map
does a candidate occupy, and is the same cell always the same cell?  How
concentrated has the population become — is the search still a population, or
one lineage wearing many ids?  And before anything is changed or erased, what
does the change actually touch?

Identity is the quiet failure mode of a MAP-Elites archive: two niches with
the same coordinates but different ids split one cell's competition into two,
so here a niche's identity *is* its coordinates — the id is derived from the
canonical axis values, and a duplicate cell or a candidate occupying two cells
is refused.  Diversity is measured, not asserted: lineage entropy is Shannon
entropy over founder shares and the effective lineage count is its exponential
(the Hill number of order one), so the two figures cannot disagree.  Blast
radius composes the sealed L05 lineage memory rather than re-walking ancestry.

Axis names come from the canonical niche schema, the entry-class partition
from the archive module that owns it, and coverage summaries from the sealed
archive builder.  Alerts recommend; nothing here promotes, evicts or erases.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from ...contracts import default_registry, validate_artifact
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...domain.ids import new_id
from ...epistemic_species_archive.archive import build_quality_diversity_map
from ...memory.v4_l05 import LineageMemory

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ATTRIBUTION_INCOMPLETE": (
        "a diversity report needs an operator or model attribution for every "
        "candidate; entropy over a partial population is a number that means "
        "nothing"
    ),
    "AXIS_UNDECLARED": (
        "a niche coordinate names an axis the canonical schema does not "
        "declare, or omits one it requires, so the cell cannot be located on "
        "the map"
    ),
    "CANDIDATE_UNKNOWN": (
        "a cartographic query named a candidate the lineage memory does not "
        "hold, so nothing can be derived about it"
    ),
    "CELL_DUPLICATED": (
        "two niches carry the same canonical coordinates, which splits one "
        "cell's competition into two records"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "map something it never validated"
    ),
    "NICHE_IDENTITY_FORGED": (
        "a niche id does not match the id its own coordinates derive, so the "
        "record claims a cell it does not occupy"
    ),
    "NICHE_OVERFULL": (
        "a niche holds more occupants than its declared capacity, which means "
        "an eviction decision was skipped rather than made"
    ),
    "NICHE_UNKNOWN": ("a cartographic input referenced a niche the map does not hold"),
    "OCCUPANCY_AMBIGUOUS": (
        "a candidate occupies more than one niche; a MAP-Elites cell assignment "
        "must be a function of the candidate"
    ),
    "ELITE_NOT_OCCUPANT": (
        "a niche names an elite that is not among its own occupants, so the "
        "cell's best result is not in the cell"
    ),
    "THRESHOLD_INVALID": (
        "an inbreeding threshold is outside its meaningful range, which would "
        "make every alert vacuous or unavoidable"
    ),
}

#: Inbreeding alerts this module may raise, with the action each recommends.
#: This is M05's own vocabulary — recommendations only, never a decision.
INBREEDING_RULES: dict[str, str] = {
    "CROSSOVER_WITHIN_SINGLE_LINEAGE": (
        "require the next crossover round to draw parents from distinct "
        "founder lineages"
    ),
    "DOMINANT_LINEAGE_SHARE_EXCEEDED": (
        "bias parent selection away from the dominant founder lineage until "
        "its share returns below the declared ceiling"
    ),
    "EFFECTIVE_LINEAGE_COUNT_BELOW_MINIMUM": (
        "seed or migrate candidates from under-represented founder lineages "
        "before the next generation"
    ),
    "OPERATOR_MONOCULTURE": (
        "re-enable or re-weight the dormant mutation operators so variation "
        "does not depend on a single operator"
    ),
}


class CartographyError(ValueError):
    """A cartographic input would damage or misrepresent the map."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise CartographyError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise CartographyError(code, message, context)


def axis_vocabulary() -> tuple[str, ...]:
    """The niche axis names, read from the schema that declares them.

    The names come from the axis object's property keys rather than its
    ``required`` list because the word "required" is itself a canonical enum
    value elsewhere (minority-report preservation status), and EF4-I22 forbids
    this module from holding another schema's vocabulary as a literal.  The
    schema-and-type suite separately asserts the two declarations agree.
    """
    document = default_registry().document("epistemic-niche")
    return tuple(document["properties"]["axis_values"]["properties"])


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def canonical_axis_values(axis_values: Mapping[str, Any]) -> dict[str, str]:
    """Exactly the declared axes, every value a non-empty string."""
    record = _require_mapping(axis_values, "axis_values")
    declared = axis_vocabulary()
    given = set(map(str, record))
    expected = set(declared)
    if given != expected:
        _fail(
            "AXIS_UNDECLARED",
            "the coordinates do not name exactly the declared axes",
            {
                "declared": sorted(expected),
                "missing": sorted(expected - given),
                "undeclared": sorted(given - expected),
            },
        )
    canonical: dict[str, str] = {}
    for axis in declared:
        value = record[axis]
        if not isinstance(value, str) or not value.strip():
            _fail(
                "AXIS_UNDECLARED",
                f"axis {axis} must carry a non-empty string value",
                {"axis": axis, "value": value},
            )
        canonical[axis] = value
    return canonical


def niche_id_for(axis_values: Mapping[str, Any]) -> str:
    """A niche's identity is its coordinates; the id is derived, never chosen.

    The same cell therefore always maps to the same id, and a record whose id
    disagrees with its own coordinates is detectable as forged.
    """
    digest = sha256_of_payload(canonical_axis_values(axis_values))
    return f"NI-{digest[len('sha256:') : len('sha256:') + 16]}"


def build_niche(
    *,
    axis_values: Mapping[str, Any],
    capacity: int,
    occupant_ids: Sequence[str],
    elite_id: str | None,
    coverage_debt: float,
) -> dict[str, Any]:
    """One canonical map cell, refused rather than repaired when inconsistent."""
    coordinates = canonical_axis_values(axis_values)
    occupants = [str(occupant) for occupant in occupant_ids]
    if len(set(occupants)) != len(occupants):
        _fail(
            "INPUT_INVALID",
            "a niche cannot hold the same occupant twice",
            {"occupant_ids": occupants},
        )
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        _fail(
            "INPUT_INVALID",
            "capacity must be a positive integer",
            {"capacity": capacity},
        )
    if len(occupants) > capacity:
        _fail(
            "NICHE_OVERFULL",
            f"{len(occupants)} occupants exceed the declared capacity {capacity}",
            {"capacity": capacity, "occupant_count": len(occupants)},
        )
    if elite_id is not None and elite_id not in occupants:
        _fail(
            "ELITE_NOT_OCCUPANT",
            f"elite {elite_id} is not among the niche's occupants",
            {"elite_id": elite_id, "occupant_ids": occupants},
        )
    niche: dict[str, Any] = {
        "niche_id": niche_id_for(coordinates),
        "axis_values": coordinates,
        "capacity": capacity,
        "occupant_ids": sorted(occupants),
        "elite_id": elite_id,
        "coverage_debt": float(coverage_debt),
    }
    niche["niche_hash"] = hash_excluding(niche, "niche_hash")
    validate_artifact("epistemic-niche", niche)
    return niche


class NicheMap:
    """Every cell of the map, with cell identity and occupancy enforced."""

    def __init__(self, niches: Sequence[Mapping[str, Any]]) -> None:
        by_id: dict[str, dict[str, Any]] = {}
        occupancy: dict[str, str] = {}
        for position, candidate_niche in enumerate(niches):
            niche = dict(_require_mapping(candidate_niche, f"niches[{position}]"))
            validate_artifact("epistemic-niche", niche)
            derived = niche_id_for(niche["axis_values"])
            if str(niche["niche_id"]) != derived:
                _fail(
                    "NICHE_IDENTITY_FORGED",
                    f"{niche['niche_id']} does not match its coordinates",
                    {"derived": derived, "stated": str(niche["niche_id"])},
                )
            if derived in by_id:
                _fail(
                    "CELL_DUPLICATED",
                    "two niches carry the same canonical coordinates",
                    {"axis_values": dict(niche["axis_values"]), "niche_id": derived},
                )
            for occupant in niche["occupant_ids"]:
                holder = occupancy.get(str(occupant))
                if holder is not None:
                    _fail(
                        "OCCUPANCY_AMBIGUOUS",
                        f"{occupant} occupies both {holder} and {derived}",
                        {"candidate_id": str(occupant), "niche_ids": [holder, derived]},
                    )
                occupancy[str(occupant)] = derived
            by_id[derived] = niche
        self._niches = by_id
        self._occupancy = occupancy

    def niche_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._niches))

    def niche(self, niche_id: str) -> Mapping[str, Any]:
        if niche_id not in self._niches:
            _fail(
                "NICHE_UNKNOWN",
                f"the map holds no niche {niche_id}",
                {"niche_id": niche_id},
            )
        return dict(self._niches[niche_id])

    def occupants(self) -> Mapping[str, str]:
        """candidate_id -> niche_id, exactly one cell per candidate."""
        return dict(self._occupancy)

    def niche_of(self, candidate_id: str) -> str | None:
        return self._occupancy.get(candidate_id)

    def occupied_niche_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                niche_id
                for niche_id, niche in self._niches.items()
                if niche["occupant_ids"]
            )
        )


def _entropy(counts: Mapping[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            share = count / total
            entropy -= share * math.log(share)
    return entropy


def _founder_of(lineage: LineageMemory, candidate_id: str) -> str:
    """The earliest ancestor; the candidate itself when it has no parents.

    A crossover child descends from several founders; for lineage accounting
    it is attributed to the founder of its first-sorted ancestor line, and the
    within-lineage crossover check below looks at the full founder set.
    """
    ancestors = lineage.ancestors_of(candidate_id)
    roots = sorted(
        ancestor for ancestor in ancestors if not lineage.parents_of(ancestor)
    )
    if not ancestors:
        return candidate_id
    return roots[0] if roots else candidate_id


def _founder_set(lineage: LineageMemory, candidate_id: str) -> tuple[str, ...]:
    ancestors = lineage.ancestors_of(candidate_id)
    if not ancestors:
        return (candidate_id,)
    roots = tuple(
        sorted(ancestor for ancestor in ancestors if not lineage.parents_of(ancestor))
    )
    return roots or (candidate_id,)


def build_lineage_diversity_report(
    *,
    lineage: LineageMemory,
    evolution_run_id: str,
    generation: int,
    operator_attribution: Mapping[str, Sequence[str]] | None = None,
    model_attribution: Mapping[str, str],
    thresholds: Mapping[str, float],
    report_id: str | None = None,
) -> dict[str, Any]:
    """Measure how concentrated the population has become.

    Operator attribution defaults to each lineage record's own declared
    mutation operators; model attribution cannot be derived from lineage
    records, so the caller must supply it for every candidate or the report
    refuses rather than publishing an entropy over a partial population.
    """
    candidates = lineage.candidates()
    if not candidates:
        _fail("INPUT_INVALID", "a diversity report needs at least one candidate")

    dominant_ceiling = thresholds.get("dominant_lineage_share_max")
    effective_floor = thresholds.get("effective_lineage_count_min")
    if (
        not isinstance(dominant_ceiling, (int, float))
        or not isinstance(effective_floor, (int, float))
        or not 0 < float(dominant_ceiling) <= 1
        or float(effective_floor) < 1
    ):
        _fail(
            "THRESHOLD_INVALID",
            "thresholds need dominant_lineage_share_max in (0, 1] and "
            "effective_lineage_count_min >= 1",
            {"thresholds": dict(thresholds)},
        )

    founder_counts: dict[str, int] = {}
    for candidate_id in candidates:
        founder = _founder_of(lineage, candidate_id)
        founder_counts[founder] = founder_counts.get(founder, 0) + 1
    # The effective count is derived from the *published* (rounded) entropy,
    # so a reader can re-derive one figure from the other exactly; deriving it
    # from the unrounded value would leave the pair off by one ulp of the
    # rounding and make the record unverifiable from its own fields.
    lineage_entropy = round(_entropy(founder_counts), 6)
    effective_lineage_count = round(math.exp(lineage_entropy), 6)
    dominant_share = max(founder_counts.values()) / len(candidates)

    operator_counts: dict[str, int] = {}
    if operator_attribution is None:
        for candidate_id in candidates:
            for operator in lineage.record(candidate_id)["mutation_operator_ids"]:
                operator_counts[str(operator)] = (
                    operator_counts.get(str(operator), 0) + 1
                )
    else:
        missing = sorted(set(candidates) - set(map(str, operator_attribution)))
        if missing:
            _fail(
                "ATTRIBUTION_INCOMPLETE",
                "operator attribution does not cover every candidate",
                {"missing": missing},
            )
        for candidate_id in candidates:
            for operator in operator_attribution[candidate_id]:
                operator_counts[str(operator)] = (
                    operator_counts.get(str(operator), 0) + 1
                )
    if not operator_counts:
        _fail(
            "ATTRIBUTION_INCOMPLETE",
            "no candidate declares a mutation operator, so operator entropy is undefined",
        )

    missing_models = sorted(set(candidates) - set(map(str, model_attribution)))
    if missing_models:
        _fail(
            "ATTRIBUTION_INCOMPLETE",
            "model attribution does not cover every candidate",
            {"missing": missing_models},
        )
    model_counts: dict[str, int] = {}
    for candidate_id in candidates:
        model = str(model_attribution[candidate_id])
        model_counts[model] = model_counts.get(model, 0) + 1

    alerts: list[str] = []
    if dominant_share > float(dominant_ceiling):
        alerts.append("DOMINANT_LINEAGE_SHARE_EXCEEDED")
    if effective_lineage_count < float(effective_floor):
        alerts.append("EFFECTIVE_LINEAGE_COUNT_BELOW_MINIMUM")
    if len(operator_counts) == 1 and len(candidates) > 1:
        alerts.append("OPERATOR_MONOCULTURE")
    for candidate_id in candidates:
        crossover_parents = [
            str(parent)
            for parent in lineage.record(candidate_id)["crossover_parent_ids"]
        ]
        if len(crossover_parents) >= 2:
            founder_sets = {
                _founder_set(lineage, parent) for parent in crossover_parents
            }
            if len(founder_sets) == 1:
                alerts.append("CROSSOVER_WITHIN_SINGLE_LINEAGE")
                break
    alerts = sorted(set(alerts))

    report: dict[str, Any] = {
        "report_id": report_id or new_id("LDR"),
        "evolution_run_id": evolution_run_id,
        "generation": int(generation),
        "lineage_entropy": lineage_entropy,
        "effective_lineage_count": effective_lineage_count,
        "dominant_lineage_share": round(dominant_share, 6),
        "operator_entropy": round(_entropy(operator_counts), 6),
        "model_entropy": round(_entropy(model_counts), 6),
        "inbreeding_alerts": alerts,
        "recommended_actions": [INBREEDING_RULES[alert] for alert in alerts],
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    validate_artifact("lineage-diversity-report", report)
    return report


def compute_blast_radius(
    *,
    lineage: LineageMemory,
    niche_map: NicheMap,
    candidate_id: str,
    island_membership: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """What changing or erasing one candidate actually touches.

    Descent comes from the sealed L05 lineage memory; the niche impact is
    which cells lose occupants and which lose their elite.  The result is a
    record, not a permission: it informs a change, it does not approve one.
    """
    if candidate_id not in lineage.candidates():
        _fail(
            "CANDIDATE_UNKNOWN",
            f"the lineage memory does not hold {candidate_id}",
            {"candidate_id": candidate_id},
        )
    descendants = lineage.descendants_of(candidate_id)
    affected = (candidate_id, *descendants)
    occupancy = niche_map.occupants()
    unmapped = sorted(candidate for candidate in affected if candidate not in occupancy)
    affected_niches = sorted(
        {occupancy[candidate] for candidate in affected if candidate in occupancy}
    )
    elites_at_risk = sorted(
        niche_id
        for niche_id in affected_niches
        if niche_map.niche(niche_id)["elite_id"] in affected
    )
    islands: list[str] = []
    if island_membership is not None:
        missing = sorted(
            candidate for candidate in affected if candidate not in island_membership
        )
        if missing:
            _fail(
                "ATTRIBUTION_INCOMPLETE",
                "island membership does not cover every affected candidate",
                {"missing": missing},
            )
        islands = sorted({str(island_membership[candidate]) for candidate in affected})

    radius: dict[str, Any] = {
        "affected_candidate_ids": list(affected),
        "affected_islands": islands,
        "affected_niche_ids": affected_niches,
        "candidate_id": candidate_id,
        "counts": {
            "affected_candidates": len(affected),
            "affected_islands": len(islands),
            "affected_niches": len(affected_niches),
            "elites_at_risk": len(elites_at_risk),
        },
        "descendant_ids": list(descendants),
        "elites_at_risk_niche_ids": elites_at_risk,
        # Candidates the map does not place are named rather than dropped: a
        # blast radius that silently ignored them would understate the impact.
        "unmapped_candidate_ids": unmapped,
    }
    radius["radius_hash"] = hash_excluding(radius, "radius_hash")
    return radius


def build_coverage_map(
    *,
    niche_map: NicheMap,
    evolution_run_id: str,
    generation: int,
    lineage_entropy: float,
    stagnant_niche_ids: Sequence[str] = (),
    map_id: str | None = None,
) -> dict[str, Any]:
    """Coverage for one generation, through the sealed archive builder.

    Occupancy is derived from the map's own cells, and a stagnant niche must
    be a niche the map actually holds; the summary arithmetic itself belongs
    to the archive module and is not restated here.
    """
    unknown = sorted(set(map(str, stagnant_niche_ids)) - set(niche_map.niche_ids()))
    if unknown:
        _fail(
            "NICHE_UNKNOWN",
            "a stagnant niche must be one the map holds",
            {"unknown": unknown},
        )
    return build_quality_diversity_map(
        evolution_run_id=evolution_run_id,
        generation=generation,
        niche_ids=list(niche_map.niche_ids()),
        occupied_niche_ids=list(niche_map.occupied_niche_ids()),
        lineage_entropy=lineage_entropy,
        stagnant_niche_ids=[str(niche) for niche in stagnant_niche_ids],
        map_id=map_id,
    )
