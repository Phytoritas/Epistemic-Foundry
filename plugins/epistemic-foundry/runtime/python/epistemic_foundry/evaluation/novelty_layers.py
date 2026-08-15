"""Multi-layer novelty that never collapses into support (EF4-I46).

Contract source: `schemas/novelty-vector.schema.json`.

"Claim, mechanism, prediction, falsifier, scope, experiment, evidence and
external prior-art novelty remain separate from support and truth."

Two separations are enforced here, and they fail differently:

* *Across layers.* The eight dimensions are kept as a vector with no aggregate
  field. A single novelty scalar would let a candidate that merely restates a
  known claim with a new experimental design read as broadly novel, because the
  one high dimension would carry the mean. Callers that need an ordering ask for
  a named dimension.
* *From support.* Novelty is a statement about what has been said before, not
  about what is true. `novelty_supports_promotion` therefore always returns
  False: there is no novelty configuration that promotes anything, and the
  function exists so that the answer is discoverable rather than assumed.

`assessment_status` is derived from which dimensions were actually computed and
whether an external prior-art search certificate is present. An unassessed
dimension must not read as zero novelty (a claim that prior art exists) or as
full novelty (a claim that it does not); it reads as unassessed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: The eight required dimensions, in the order the invariant names them.
NOVELTY_LAYERS: tuple[str, ...] = (
    "claim_semantic",
    "mechanism_topology",
    "prediction_signature",
    "falsifier_signature",
    "scope_shift",
    "experiment_design",
    "evidence_basis",
    "external_prior_art",
)

#: The one dimension that cannot be computed from the local corpus alone.
EXTERNAL_LAYER = "external_prior_art"

#: Statuses that permit stating novelty at all, from the schema enum.
CLAIMABLE_STATUSES: frozenset[str] = frozenset({"ASSESSED", "PARTIAL"})


class NoveltyVectorRefused(ValueError):
    """A novelty vector is incomplete or internally inconsistent."""


def build_novelty_vector(
    *,
    candidate_id: str,
    dimensions: Mapping[str, float],
    nearest_candidate_ids: Sequence[str],
    external_search_certificate_id: str,
    uncertainties: Sequence[str],
    external_search_completed: bool,
    novelty_vector_id: str | None = None,
    computed_at: str | None = None,
) -> dict[str, Any]:
    """Build a per-layer novelty vector with a derived assessment status.

    `assessment_status` is not a parameter. A caller that both computes the
    dimensions and declares how well they were computed can label a search it
    never ran as `ASSESSED`, which is the failure `EF4-I47` also guards on the
    single-status path.

    An out-of-range or non-numeric dimension is refused here rather than left to
    the schema so the message names the offending layer.
    """
    missing = [layer for layer in NOVELTY_LAYERS if layer not in dimensions]
    if missing:
        raise NoveltyVectorRefused(
            f"novelty layers {missing} were not computed; an omitted layer would be read as "
            "either no novelty or full novelty, and it is neither"
        )
    unknown = sorted(set(dimensions) - set(NOVELTY_LAYERS))
    if unknown:
        raise NoveltyVectorRefused(
            f"layers {unknown} are not canonical novelty dimensions; the vocabulary is "
            f"{NOVELTY_LAYERS}"
        )
    for layer in NOVELTY_LAYERS:
        value = dimensions[layer]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NoveltyVectorRefused(
                f"layer {layer} carries {value!r}; novelty per layer is a number in 0..1"
            )
        if not 0.0 <= float(value) <= 1.0:
            raise NoveltyVectorRefused(
                f"layer {layer} is {value}, outside 0..1; a novelty score outside the unit "
                "interval cannot be compared against another candidate's"
            )

    if external_search_completed:
        status = "ASSESSED" if not uncertainties else "PARTIAL"
    else:
        # The external layer is the only one a local corpus cannot settle. Without
        # a completed external search the vector is partial at best, and claiming
        # otherwise would turn "we did not look outside" into "nothing exists
        # outside".
        status = "PARTIAL" if any(
            float(dimensions[layer]) > 0.0 for layer in NOVELTY_LAYERS if layer != EXTERNAL_LAYER
        ) else "UNASSESSED"

    vector: dict[str, Any] = {
        "novelty_vector_id": novelty_vector_id or new_id("NV"),
        "candidate_id": candidate_id,
        "dimensions": {layer: float(dimensions[layer]) for layer in NOVELTY_LAYERS},
        "nearest_candidate_ids": list(nearest_candidate_ids),
        "external_search_certificate_id": external_search_certificate_id,
        "assessment_status": status,
        "uncertainties": list(uncertainties),
        "computed_at": computed_at or utc_now_iso(),
    }
    validate_artifact("novelty-vector", vector)
    return vector


def failed_novelty_vector(
    *,
    candidate_id: str,
    external_search_certificate_id: str,
    reasons: Sequence[str],
    novelty_vector_id: str | None = None,
    computed_at: str | None = None,
) -> dict[str, Any]:
    """Record a novelty computation that failed, without inventing scores.

    Zero is not a safe placeholder: on this scale zero means "identical to known
    prior art", which is a positive finding. A failed assessment therefore records
    `FAILED` with the reasons and leaves every dimension at zero *only* alongside
    that status, which `novelty_is_claimable` refuses.
    """
    if not reasons:
        raise NoveltyVectorRefused(
            "a failed novelty assessment must state why; an unexplained failure cannot be "
            "retried or distinguished from a completed search"
        )
    vector: dict[str, Any] = {
        "novelty_vector_id": novelty_vector_id or new_id("NV"),
        "candidate_id": candidate_id,
        "dimensions": {layer: 0.0 for layer in NOVELTY_LAYERS},
        "nearest_candidate_ids": [],
        "external_search_certificate_id": external_search_certificate_id,
        "assessment_status": "FAILED",
        "uncertainties": list(reasons),
        "computed_at": computed_at or utc_now_iso(),
    }
    validate_artifact("novelty-vector", vector)
    return vector


def novelty_is_claimable(vector: Mapping[str, Any]) -> bool:
    """True only for a status that permits stating novelty at all."""
    return str(vector.get("assessment_status")) in CLAIMABLE_STATUSES


def novel_layers(vector: Mapping[str, Any], *, threshold: float) -> list[str]:
    """Layers exceeding `threshold`, reported by name rather than as a count.

    Returning names keeps the answer to "novel how?" attached to the answer to
    "novel?". A count would let two candidates novel in disjoint respects appear
    equivalent.
    """
    if not 0.0 <= threshold <= 1.0:
        raise NoveltyVectorRefused(f"threshold {threshold} is outside 0..1")
    if not novelty_is_claimable(vector):
        return []
    dimensions = vector.get("dimensions", {})
    return [layer for layer in NOVELTY_LAYERS if float(dimensions.get(layer, 0.0)) > threshold]


def novelty_supports_promotion(vector: Mapping[str, Any]) -> bool:
    """Always False: novelty is not support, at any layer or magnitude.

    This exists as a named answer rather than an omission. A caller looking for
    "may this novelty promote?" finds False here instead of finding nothing and
    reaching for the highest dimension.
    """
    return False
