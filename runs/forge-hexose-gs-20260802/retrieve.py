#!/usr/bin/env python3
"""FORGE run: multi-lane retrieval over the paper-curation corpus.

Deterministic, no clock, no randomness: the corpus snapshot identity is the
sorted content hashes of every document read, and every lane receipt records
the exact patterns used. Lane separation matters epistemically: a lane that
returns nothing is ABSENCE OF EVIDENCE IN THAT LANE, never evidence of absence
overall (epistemic_foundry.retrieval.search_state).

Hypothesis under test (decomposed in HYPOTHESIS below):
  Stomatal conductance is modulated by hexose; on equally clear days morning
  stomatal opening is reduced because the previous day had adequate light but
  insufficient temperature for growth, so overnight conversion of hexose into
  structural carbohydrate was low, and the residual hexose suppresses morning
  stomatal opening.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

CORPUS = Path(r"C:\dev\insight\paper-curation\docs\papers")
RUN_DIR = Path(__file__).resolve().parent
RUN_ID = "FORGE-HEXOSE-GS-20260802"
RECORDED_AT = "2026-08-02T12:00:00.000Z"  # caller-supplied; no clock in this path

#: Each sub-claim of the composite hypothesis, kept separable so the verdict
#: can differ per link instead of collapsing into one true/false.
HYPOTHESIS = {
    "hypothesis_id": "HYP-HEXOSE-GS-001",
    "statement": (
        "Stomatal conductance is modulated by hexose. On otherwise-equivalent "
        "clear days, morning stomatal opening is reduced when the preceding day "
        "had adequate light but temperature too low for growth, because reduced "
        "overnight conversion of hexose into structural carbohydrate leaves "
        "residual hexose that suppresses stomatal opening."
    ),
    "sub_claims": {
        "C1": "Hexose (glucose/fructose) modulates stomatal aperture/conductance.",
        "C2": "Low night temperature limits growth and structural-carbohydrate conversion (sink activity).",
        "C3": "Reduced overnight structural conversion leaves elevated residual leaf hexose at dawn.",
        "C4": "Elevated dawn leaf hexose causally reduces morning stomatal opening on a clear day.",
    },
}

#: Lane = an independent search modality. Terms are lowercase regex fragments.
LANES: dict[str, dict] = {
    "L1_sugar_sensing": {
        "purpose": "hexose and sugar-sensing machinery (C1, C3, C4)",
        "terms": [
            r"hexose", r"hexokinase", r"\bhxk1?\b", r"glucose sensing", r"glucose signal",
            r"sugar sensing", r"sugar signal", r"sugar-sensing", r"trehalose[- ]6[- ]phosphate",
            r"\bt6p\b", r"fructose", r"glucose",
        ],
    },
    "L2_stomata": {
        "purpose": "stomatal response surface (C1, C4)",
        "terms": [
            r"stomatal conductance", r"stomatal aperture", r"guard cell", r"stomatal opening",
            r"stomatal closure", r"stomatal response", r"\bg\Ss\b", r"stomata",
        ],
    },
    "L3_diurnal": {
        "purpose": "time-of-day structure of the observation (C4)",
        "terms": [
            r"diurnal", r"\bdawn\b", r"\bmorning\b", r"midday", r"afternoon",
            r"time of day", r"circadian", r"hysteresis", r"\bpredawn\b", r"pre-dawn",
        ],
    },
    "L4_night_temperature": {
        "purpose": "night temperature as the upstream driver (C2)",
        "terms": [
            r"night temperature", r"nocturnal temperature", r"night-time temperature",
            r"nighttime temperature", r"day/night temperature", r"day-night temperature",
            r"\bchilling\b", r"cool night", r"cold night", r"low night", r"\bdif\b",
            r"suboptimal temperature", r"temperature sum",
        ],
    },
    "L5_carbon_partitioning": {
        "purpose": "starch/sugar turnover and structural conversion (C2, C3)",
        "terms": [
            r"starch degradation", r"starch mobili[sz]ation", r"starch turnover",
            r"structural carbohydrate", r"non-?structural carbohydrate", r"\bnsc\b",
            r"cell wall synthesis", r"sink strength", r"sink limitation", r"sink activity",
            r"sucrose export", r"carbohydrate accumulation", r"carbon starvation",
            r"source-sink", r"source/sink",
        ],
    },
    "L6_competing_mechanism": {
        "purpose": "rival explanations for reduced morning gs (adversarial lane)",
        "terms": [
            r"root hydraulic conductivit", r"aquaporin", r"abscisic acid", r"\baba\b",
            r"photosynthetic induction", r"vapou?r pressure deficit", r"\bvpd\b",
            r"hydraulic conductance", r"leaf water potential", r"stomatal patchiness",
            r"mesophyll conductance",
        ],
    },
}

WINDOW = 420  # chars of context captured on each side of a co-occurrence hit


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def compile_lanes() -> dict[str, list[tuple[str, re.Pattern]]]:
    compiled: dict[str, list[tuple[str, re.Pattern]]] = {}
    for lane, spec in LANES.items():
        compiled[lane] = [(t, re.compile(t, re.IGNORECASE)) for t in spec["terms"]]
    return compiled


def main() -> int:
    compiled = compile_lanes()
    docs = sorted(CORPUS.glob("*/text.md"))
    if not docs:
        raise SystemExit(f"no text.md under {CORPUS}")

    corpus_units: list[dict] = []
    per_doc: list[dict] = []
    lane_doc_counts = {lane: 0 for lane in LANES}
    lane_hit_counts = {lane: 0 for lane in LANES}

    for path in docs:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        doc_id = path.parent.name
        digest = sha256_text(text)
        corpus_units.append(
            {
                "document_id": doc_id,
                "path": path.as_posix(),
                "sha256": digest,
                "char_count": len(text),
            }
        )
        lower = text.lower()

        lane_hits: dict[str, dict] = {}
        for lane, terms in compiled.items():
            term_counts: dict[str, int] = {}
            positions: list[int] = []
            for raw, rx in terms:
                found = [m.start() for m in rx.finditer(lower)]
                if found:
                    term_counts[raw] = len(found)
                    positions.extend(found[:200])
            if term_counts:
                lane_doc_counts[lane] += 1
                lane_hit_counts[lane] += sum(term_counts.values())
                lane_hits[lane] = {
                    "term_counts": term_counts,
                    "total": sum(term_counts.values()),
                    "first_positions": sorted(positions)[:40],
                }

        if not lane_hits:
            continue

        lanes_present = set(lane_hits)
        # Co-occurrence: a mechanistic hit needs sugar-sensing AND stomata terms
        # inside the same window, not merely in the same paper.
        cooc_spans: list[dict] = []
        if "L1_sugar_sensing" in lane_hits and "L2_stomata" in lane_hits:
            l2_positions = sorted(lane_hits["L2_stomata"]["first_positions"])
            for p1 in lane_hits["L1_sugar_sensing"]["first_positions"][:40]:
                near = [p2 for p2 in l2_positions if abs(p2 - p1) <= WINDOW]
                if not near:
                    continue
                start = max(0, p1 - WINDOW)
                end = min(len(text), p1 + WINDOW)
                snippet = text[start:end].replace("\n", " ")
                cooc_spans.append(
                    {
                        "char_start": start,
                        "char_end": end,
                        "quote": snippet.strip(),
                    }
                )
                if len(cooc_spans) >= 6:
                    break

        per_doc.append(
            {
                "document_id": doc_id,
                "sha256": digest,
                "lanes": {k: v["total"] for k, v in lane_hits.items()},
                "lane_terms": {k: v["term_counts"] for k, v in lane_hits.items()},
                "lane_count": len(lanes_present),
                "mechanistic_cooccurrence_count": len(cooc_spans),
                "cooccurrence_spans": cooc_spans,
            }
        )

    corpus_units.sort(key=lambda u: u["document_id"])
    snapshot_id = "CSNAP-" + hashlib.sha256(
        "".join(u["sha256"] for u in corpus_units).encode("ascii")
    ).hexdigest()[:32]

    def score(row: dict) -> tuple:
        lanes = row["lanes"]
        core = row["mechanistic_cooccurrence_count"] * 10
        sugar = min(lanes.get("L1_sugar_sensing", 0), 60)
        stom = min(lanes.get("L2_stomata", 0), 60)
        diur = min(lanes.get("L3_diurnal", 0), 30)
        night = min(lanes.get("L4_night_temperature", 0), 30)
        carb = min(lanes.get("L5_carbon_partitioning", 0), 30)
        return (core + sugar + stom + diur + night + carb, row["lane_count"], row["document_id"])

    ranked = sorted(per_doc, key=score, reverse=True)

    # Targeted sub-corpora, one per causal link, so no link is judged from a
    # ranking tuned for another link.
    def has(row: dict, lane: str, minimum: int = 1) -> bool:
        return row["lanes"].get(lane, 0) >= minimum

    sets = {
        "C1_hexose_x_stomata": [r for r in ranked if r["mechanistic_cooccurrence_count"] > 0],
        "C2_night_temp_x_growth": [
            r for r in ranked if has(r, "L4_night_temperature", 2) and has(r, "L5_carbon_partitioning", 2)
        ],
        "C3_overnight_carbon_turnover": [
            r for r in ranked if has(r, "L5_carbon_partitioning", 3) and has(r, "L3_diurnal", 3)
        ],
        "C4_morning_gs": [
            r for r in ranked if has(r, "L2_stomata", 3) and has(r, "L3_diurnal", 3)
        ],
        "RIVALS_competing_mechanisms": [
            r
            for r in ranked
            if has(r, "L6_competing_mechanism", 3) and has(r, "L2_stomata", 3) and has(r, "L3_diurnal", 2)
        ],
    }

    lane_receipts = []
    for lane, spec in LANES.items():
        state = "RESULTS_FOUND" if lane_doc_counts[lane] else "NO_RESULTS_IN_LANE"
        lane_receipts.append(
            {
                "lane_id": lane,
                "purpose": spec["purpose"],
                "patterns": spec["terms"],
                "documents_matched": lane_doc_counts[lane],
                "total_term_hits": lane_hit_counts[lane],
                "lane_state": state,
                "interpretation": (
                    "absence in this lane is absence of evidence in this lane only"
                    if state == "NO_RESULTS_IN_LANE"
                    else "lane returned candidates; relevance is decided downstream, not here"
                ),
            }
        )

    out = {
        "run_id": RUN_ID,
        "recorded_at_utc": RECORDED_AT,
        "hypothesis": HYPOTHESIS,
        "corpus_snapshot": {
            "snapshot_id": snapshot_id,
            "root": CORPUS.as_posix(),
            "document_count": len(corpus_units),
            "total_chars": sum(u["char_count"] for u in corpus_units),
        },
        "lane_receipts": lane_receipts,
        "candidate_counts": {k: len(v) for k, v in sets.items()},
        "top_by_set": {
            k: [
                {
                    "document_id": r["document_id"],
                    "lanes": r["lanes"],
                    "cooc": r["mechanistic_cooccurrence_count"],
                }
                for r in v[:25]
            ]
            for k, v in sets.items()
        },
    }

    (RUN_DIR / "corpus-snapshot.json").write_text(
        json.dumps({"snapshot_id": snapshot_id, "units": corpus_units}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUN_DIR / "retrieval-run.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RUN_DIR / "candidates-detail.json").write_text(
        json.dumps({k: v[:30] for k, v in sets.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "snapshot_id": snapshot_id,
        "documents": len(corpus_units),
        "lane_documents": lane_doc_counts,
        "candidate_counts": out["candidate_counts"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
