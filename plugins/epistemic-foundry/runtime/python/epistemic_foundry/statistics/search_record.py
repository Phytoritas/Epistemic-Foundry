"""The adaptive-search statistical record as a set (EF4-I53).

"Evolutionary search records candidate families, repeated tests, sequential
decisions, multiplicity and selective inference."

The individual artifacts already exist: `statistics/sequential.py` holds the
look-by-look ledger, `statistics/multiplicity.py` the family-wide correction, and
`statistics/selective.py` the winner's-curse report. What this module adds is the
requirement that they arrive *together* and describe *the same family*.

That combination is the point. Each artifact alone permits a true statement that
is collectively misleading:

* a sequential ledger without a multiplicity adjustment accounts for looking
  often at one hypothesis while ignoring that a thousand were tried;
* a multiplicity adjustment without a selective-inference report corrects the
  p-value of the winner without correcting its effect size;
* a selective-inference report without a sequential ledger corrects for choosing
  the maximum while ignoring when the search chose to stop.

So `require_search_statistics` refuses a partial set and refuses a set whose
members reference different families or candidates. `MASTER_SPEC.md` §28 also
requires the hidden-exposure log, candidate family/lineage, selection and stop
events, and the replication result, so those are named ids on the record rather
than optional extras.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.hashing import sha256_of_payload
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: The artifacts MASTER_SPEC.md §28 requires for an adaptive search. Named as a
#: tuple so a missing member is reported by name rather than as a count.
REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "sequential_testing_ledger_id",
    "multiple_testing_adjustment_id",
    "selective_inference_report_id",
    "hidden_exposure_log_id",
    "candidate_lineage_id",
    "replication_result_id",
)


class SearchStatisticsIncomplete(ValueError):
    """The adaptive-search statistical record is missing or inconsistent."""


def missing_statistical_artifacts(record: Mapping[str, Any]) -> list[str]:
    """Which required artifacts are absent, reported by name.

    An empty string counts as absent. A record carrying `""` for an artifact id
    would satisfy a key-presence check while referencing nothing.
    """
    return [
        name
        for name in REQUIRED_ARTIFACTS
        if not isinstance(record.get(name), str) or not str(record.get(name)).strip()
    ]


def build_search_statistics_record(
    *,
    evolution_run_id: str,
    family_id: str,
    candidate_id: str,
    sequential_ledger: Mapping[str, Any],
    multiplicity_adjustment: Mapping[str, Any],
    selective_report: Mapping[str, Any],
    hidden_exposure_log_id: str,
    candidate_lineage_id: str,
    replication_result_id: str,
    record_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Bind the five statistical artifacts to one family and candidate.

    The artifacts are passed as records rather than as ids so their `family_id`
    and `candidate_id` can be compared here. Accepting ids alone would make the
    consistency check impossible at the only point where all five are in hand,
    and a record assembled from artifacts about different families is the
    misleading-but-individually-true case this invariant targets.
    """
    ledger_family = str(sequential_ledger.get("family_id", ""))
    adjustment_family = str(multiplicity_adjustment.get("family_id", ""))
    report_candidate = str(selective_report.get("candidate_id", ""))

    mismatches: list[str] = []
    if ledger_family != family_id:
        mismatches.append(
            f"sequential ledger covers family {ledger_family!r}, not {family_id!r}"
        )
    if adjustment_family != family_id:
        mismatches.append(
            f"multiplicity adjustment covers family {adjustment_family!r}, not {family_id!r}"
        )
    if report_candidate != candidate_id:
        mismatches.append(
            f"selective-inference report covers candidate {report_candidate!r}, "
            f"not {candidate_id!r}"
        )
    if mismatches:
        raise SearchStatisticsIncomplete(
            "refusing a statistical record assembled from unrelated artifacts: "
            + "; ".join(mismatches)
        )

    # The number of tests the family actually ran must not be smaller than the
    # number of looks the ledger recorded. A correction computed over fewer tests
    # than were run is an under-correction, which is the direction that produces
    # false positives.
    looks = len(sequential_ledger.get("entries", []))
    raw_tests = int(multiplicity_adjustment.get("raw_test_count", 0))
    if raw_tests < looks:
        raise SearchStatisticsIncomplete(
            f"multiplicity adjustment corrects for {raw_tests} tests while the sequential "
            f"ledger records {looks} looks; correcting for fewer tests than were run "
            "under-states the false-positive rate"
        )

    record: dict[str, Any] = {
        "record_id": record_id or new_id("SSR"),
        "evolution_run_id": evolution_run_id,
        "family_id": family_id,
        "candidate_id": candidate_id,
        "sequential_testing_ledger_id": str(sequential_ledger.get("ledger_id", "")),
        "multiple_testing_adjustment_id": str(multiplicity_adjustment.get("adjustment_id", "")),
        "selective_inference_report_id": str(selective_report.get("report_id", "")),
        "hidden_exposure_log_id": hidden_exposure_log_id,
        "candidate_lineage_id": candidate_lineage_id,
        "replication_result_id": replication_result_id,
        "selection_events": list(sequential_ledger.get("selection_events", [])),
        "winner_curse_risk": str(selective_report.get("winner_curse_risk", "unknown")),
        "promotion_recommendation": str(
            selective_report.get("promotion_recommendation", "BLOCK")
        ),
        "created_at": created_at or utc_now_iso(),
    }
    missing = missing_statistical_artifacts(record)
    if missing:
        raise SearchStatisticsIncomplete(
            f"adaptive search is missing required statistical artifacts {missing}; each one "
            "accounts for a different way the search could have found this candidate"
        )
    record["record_hash"] = sha256_of_payload(
        {key: value for key, value in record.items() if key != "record_hash"}
    )
    return record


def require_search_statistics(record: Mapping[str, Any]) -> None:
    """Raise unless every required artifact is present on the record."""
    missing = missing_statistical_artifacts(record)
    if missing:
        raise SearchStatisticsIncomplete(
            f"refusing to treat an adaptive search as accounted for: missing {missing}"
        )


def search_permits_promotion(record: Mapping[str, Any]) -> bool:
    """True only for a complete record whose selective report says `ALLOW`.

    The recommendation is read from the record rather than re-derived, because the
    selective-inference report is the authority for it. Completeness is checked
    first so an incomplete record cannot pass on the strength of a copied
    recommendation.
    """
    if missing_statistical_artifacts(record):
        return False
    return str(record.get("promotion_recommendation")) == "ALLOW"
