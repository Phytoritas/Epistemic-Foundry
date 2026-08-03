#!/usr/bin/env python3
"""Deterministic gates and adjudication for FORGE-HEXOSE-GS-20260802.

The parliament's briefs are model judgment; this file is the part that cannot be
argued with. Gate decisions are canonical artifacts, and `build_adjudication`
refuses to record any advancing promotion while a gate has failed — so the run
demonstrates the refusal rather than merely asserting that it would happen.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\dev\insight\Epistemic-Foundry")
sys.path.insert(0, str(ROOT / "src"))

from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402
from epistemic_foundry.evidence_parliament.adjudication import (  # noqa: E402
    GateOverrideAttempted,
    build_adjudication,
)

RUN_DIR = Path(__file__).resolve().parent
RUN_ID = "FORGE-HEXOSE-GS-20260802"
HYP = "HYP-HEXOSE-GS-001"
AT = "2026-08-02T12:00:00.000Z"
POLICY = "sha256:" + hashlib.sha256(b"FORGE-HEXOSE-GS-20260802/parliament-policy/v1").hexdigest()


def gate(name: str, status: str, reasons: list[str], evidence_ids: list[str], *, non_waivable: bool = True) -> dict:
    record = {
        "gate_id": "GATE-" + hashlib.sha256(f"{RUN_ID}|{name}".encode()).hexdigest()[:16].upper(),
        "gate_version": "1.0.0",
        "run_id": RUN_ID,
        "name": name,
        "status": status,
        "reasons": reasons,
        "evidence_ids": evidence_ids,
        "input_artifact_ids": ["grounded-claims.json", "grounding-report.json"],
        "policy_bundle_hash": POLICY,
        "decision": status,
        "blocker_ids": [] if status == "PASS" else [name],
        "waiver_authority": None,
        "waiver_reason": None,
        "evaluated_at": AT,
        "created_at": AT,
        "policy_version": "1.0.0",
        "non_waivable": non_waivable,
        "evaluator_type": "model_assisted" if status != "PASS" or "grounding" not in name else "deterministic",
        "input_hash": "sha256:" + hashlib.sha256(json.dumps(reasons, sort_keys=True).encode()).hexdigest(),
        "decision_hash": "",
    }
    record["decision_hash"] = hash_excluding(record, "decision_hash")
    validate_artifact("gate-decision", record)
    return record


def main() -> int:
    grounding = json.loads((RUN_DIR / "grounding-report.json").read_text(encoding="utf-8"))
    claims = json.loads((RUN_DIR / "grounded-claims.json").read_text(encoding="utf-8"))["claims"]

    def ids_for(link: str, bearing: str | None = None) -> list[str]:
        out = []
        for c in claims:
            if link in (c.get("relevance_to") or []):
                if bearing is None or c.get("bearing_on_hypothesis") == bearing:
                    out.append(c["grounded_claim_id"])
        return out

    c4_support = ids_for("C4", "supports")
    c4_contra = ids_for("C4", "contradicts")

    gates = {
        "claim_span_grounding": gate(
            "claim_span_grounding", grounding["gate"]["status"],
            [f"{grounding['counts']['claims_verified']}/{grounding['counts']['claims_submitted']} spans re-extracted byte-identically"],
            [c["grounded_claim_id"] for c in claims][:50],
        ),
        "causal_identification": gate(
            "causal_identification", "FAIL",
            ["previous-night temperature is a common cause of the exposure and of at least six other direct determinants of morning gs (root hydraulics, circadian phase, dawn leaf temperature, photosynthetic induction, guard-cell starch, morning VPD): seven backdoor paths",
             "the exclusion restriction required to identify the hexose path is contradicted by established physiology, so the design is NOT_IDENTIFIED rather than assumption-dependent",
             "whole-leaf hexose is a PROXY for guard-cell hexose and the proxy error is differential with respect to night temperature, so the bias is not attenuation-toward-null"],
            ids_for("C4"),
        ),
        "method_audit": gate(
            "method_audit", "FAIL",
            ["C4's entire affirmative base is 3 modeling claims plus one 1979 background assertion; zero direct measurements support C4 while 27 of 38 C4 claims contradict",
             "the only observed closure is at 100 mM and is reproduced by an equi-osmolar mannitol control, so it is attributable to osmolarity rather than to hexose sensing",
             "closure concentrations are 18-250x the reported physiological apoplastic range (0.4-5.5 mM), and within that range the measured sign reverses to enhancement of opening",
             "no experiment in the corpus shows glucose or fructose at a physiological apoplastic concentration reducing gs",
             "statistical substrate: 0/107 effect sizes, 0/107 sample sizes, 1/107 p-values; treatment is confounded with chamber in every temperature experiment (effective n = 1 per level)"],
            c4_support + c4_contra,
        ),
        "scope_transfer": gate(
            "scope_transfer", "FAIL",
            ["of 12 direct measurements joining sugar to stomata, 10 are Arabidopsis or Vicia faba and exactly one is in a target crop - and that one is the null-mediator result",
             "the apoplastic sugar messenger is light-gated in this corpus: apoplastic fluid from leaves kept in darkness is inert and petiole-fed sucrose raised gs under red light but not in darkness, while the hypothesis needs the route to act at dawn when transpiration is near zero",
             "dawn evidence has guard-cell hexose enabling opening; closure is scoped to the carbon-saturated afternoon, so the hypothesis imports the afternoon sign into the dawn phase",
             "the exposure construct (whole-leaf, stock-semantics, compartment-blind residual hexose) is a different variable from the guard-cell-accessible, flow-determined concentration the mechanism requires"],
            ids_for("C1") + ids_for("C4"),
        ),
        "evidence_direction_balance": gate(
            "evidence_direction_balance", "FAIL",
            [f"C4: {len(c4_support)} supporting vs {len(c4_contra)} contradicting grounded claims",
             "the supporting side is predominantly review and modeling layer while the contradicting side carries the direct measurements"],
            c4_support + c4_contra,
        ),
    }

    # ---- Demonstration: the machinery refuses an advancing verdict on failed gates
    refusal = None
    try:
        build_adjudication(
            run_id=RUN_ID, hypothesis_id=HYP,
            gate_decisions=list(gates.values()),
            brief_ids=["BRIEF-DEFENDER", "BRIEF-PROSECUTOR"],
            cross_examination_ids=["XEX-DEDUCTIVE", "XEX-CAUSAL"],
            verdict="CONDITIONAL",
            promotion_recommendation="CANDIDATE",   # <- advancing
            rationale="attempt to record the owner's hypothesis as a CANDIDATE despite failed gates",
            strongest_support_id=(c4_support or [None])[0],
            strongest_counterevidence_id=(c4_contra or [None])[0],
            adjudication_id="ADJ-DEMO-OVERRIDE", created_at=AT,
        )
    except GateOverrideAttempted as exc:
        refusal = str(exc)

    # ---- The honest record for the hypothesis AS STATED
    as_stated = build_adjudication(
        run_id=RUN_ID, hypothesis_id=HYP,
        gate_decisions=list(gates.values()),
        brief_ids=["BRIEF-DEFENDER", "BRIEF-PROSECUTOR"],
        cross_examination_ids=["XEX-DEDUCTIVE", "XEX-CAUSAL", "XEX-METHOD", "XEX-SCOPE", "XEX-ABDUCTIVE"],
        verdict="CONTRADICTED",
        promotion_recommendation="BLOCK",
        rationale=(
            "As stated, the chain fails on four independent grounds. The mechanism is asserted at the "
            "dawn phase and in the guard-cell compartment, where every direct measurement in the corpus "
            "shows hexose ENABLING opening (loss of the dawn guard-cell glucose pool increases the opening "
            "time constant by 40 min). The closure literature it relies on sits 18-250x above the physiological "
            "apoplastic concentration and is reproduced by an equi-osmolar mannitol control, so it is osmotic "
            "rather than hexose sensing. The premise that a cool night leaves residual leaf hexose is contested "
            "by the only pre-dawn-sampled experiment, which is a null, and the causal path is not identified "
            "observationally because night temperature is a common cause of the exposure and of six other "
            "determinants of morning conductance. BLOCK applies to the mechanism as stated, not to the "
            "observation, which remains real and worth explaining."
        ),
        strongest_support_id=(c4_support or [None])[0],
        strongest_counterevidence_id=(c4_contra or [None])[0],
        minority_report_ids=["MIN-HEXOSE-DAWN-CARBON-REPLETE"],
        unresolved_issue_ids=["EXPLANANDUM-AMBIGUITY", "C3-SIGN-CONFLICT", "DAWN-CARBON-REPLETE-CELL-UNMEASURED"],
        scope_narrowing=[
            "verdict applies to (guard-cell hexose) x (greenhouse fruiting crop) x (dawn/dark phase)",
            "does not apply to the night-temperature -> morning-gs association, which is not adjudicated here",
        ],
        adjudication_id="ADJ-HEXOSE-AS-STATED", created_at=AT,
    )

    # ---- The reformulated, defensible claim: its own gates, honestly evaluated
    b1_gates = {
        "claim_span_grounding": gates["claim_span_grounding"],
        "scope_transfer_b1": gate(
            "scope_transfer_b1", "PASS",
            ["C2 transfers cleanly and quantitatively to greenhouse tomato with published temperature parameters (TBase_24 = 12, TOpt1_24 = 18, TOpt2_24 = 22 C)",
             "the sink-demand -> stomatal-resistance link is directly measured in cucumber at constant 25 C day and night, i.e. with temperature held",
             "scope auditor explicitly does not veto the temperature-worded, crop-scoped association or C2 alone"],
            ids_for("C2"),
        ),
        "method_audit_b1": gate(
            "method_audit_b1", "PASS",
            ["C2's best evidence is a randomized intervention (fruit-cuvette temperature switch 27.5 -> 17.5 C changed fruit growth rate within one day)",
             "method auditor does not veto C2 at intervention-supported level when scoped to sink organs rather than the mature source leaf"],
            ids_for("C2"),
        ),
        "causal_identification_b1": gate(
            "causal_identification_b1", "FAIL",
            ["the sink-status mediator is not identified observationally either: night temperature remains a common cause of sink activity and of the rival determinants of morning gs",
             "a randomized night-temperature design identifies the night-temperature effect but not the mediator"],
            ids_for("C2") + ids_for("C4"),
            non_waivable=False,
        ),
    }
    b1 = build_adjudication(
        run_id=RUN_ID, hypothesis_id="HYP-HEXOSE-GS-001-B1",
        gate_decisions=list(b1_gates.values()),
        brief_ids=["BRIEF-DEFENDER"],
        cross_examination_ids=["XEX-CAUSAL", "XEX-SCOPE"],
        verdict="UNDERDETERMINED",
        promotion_recommendation="BLOCK",
        rationale=(
            "The reformulated claim - morning gs is reduced after nights cool enough to suppress sink activity, "
            "mediated by reduced sink demand rather than by residual hexose - survives the scope and method audits "
            "and has a direct crop-scale demonstration in which sink limitation alone depressed conductance at "
            "constant temperature. It is nevertheless recorded as BLOCK rather than CANDIDATE because its own "
            "causal-identification gate fails: the mediator is no better identified than the hexose one. The gate, "
            "not the argument, sets this ceiling, and it lifts the moment an intervention design supplies the missing "
            "identification."
        ),
        strongest_support_id=(ids_for("C2", "supports") or [None])[0],
        strongest_counterevidence_id=(ids_for("C2", "contradicts") or [None])[0],
        unresolved_issue_ids=["MEDIATOR-NOT-IDENTIFIED"],
        scope_narrowing=["greenhouse tomato / cucumber", "night temperature band where growth is inhibited but carbon supply is not"],
        adjudication_id="ADJ-HEXOSE-B1-REFORMULATED", created_at=AT,
    )

    minority = {
        "minority_report_id": "MIN-HEXOSE-DAWN-CARBON-REPLETE",
        "run_id": RUN_ID,
        "author_role": "defender",
        "minority_claim": (
            "Every corpus source that establishes hexose as a positive requirement for dawn stomatal opening "
            "measured a NORMAL dawn, which is carbon-depleted by construction. The owner's scenario specifies a "
            "bright prior day followed by a night too cool to consume the surplus - a carbon-replete dawn. That "
            "combination is an empty cell in the corpus: the required guard-cell apoplastic concentration band "
            "(above the 0.4-5.5 mM measured range, below the 30 mM where opposition first appears) contains zero "
            "measurements. The hypothesis is therefore unmeasured in its own regime, not refuted in it."
        ),
        "evidence_ids": (c4_support + c4_contra)[:12],
        "why_majority_may_be_wrong": (
            "The majority reads the dawn evidence as fixing the sign of the hexose-aperture derivative. It does not: "
            "the positive branch is itself carbon-status-gated - exogenous sugar promoted opening only under carbon "
            "starvation and had no effect under a normal photoperiod - so a loss-of-function result obtained at a "
            "carbon-depleted dawn cannot determine the derivative's sign at a carbon-replete dawn. The majority also "
            "treats the 5-30 mM gap as absence of effect when it is absence of measurement."
        ),
        "unresolved_test": (
            "Measure guard-cell apoplastic and cytosolic glucose and fructose at -60 and -10 min before effective light "
            "onset on matched clear mornings contrasted on prior-day light and night temperature, and pair them with a "
            "continuous gs time course; then run a dose-response across 1-30 mM with an equi-osmolar mannitol arm and a "
            "non-metabolizable analogue. Cheapest prior falsifier: does the morning depression persist after cool nights "
            "that followed a LOW-light day? If it does, the carbon-carryover family fails regardless of mediator."
        ),
        "expected_information_gain": 0.72,
        "preservation_status": "required",
        "created_at": AT,
        "report_hash": "",
    }
    minority["report_hash"] = hash_excluding(minority, "report_hash")
    validate_artifact("minority-report", minority)

    out = {
        "run_id": RUN_ID,
        "recorded_at_utc": AT,
        "gates": {name: {"status": g["status"], "gate_id": g["gate_id"]} for name, g in gates.items()},
        "gate_override_refusal": refusal,
        "adjudication_as_stated": as_stated,
        "adjudication_b1_reformulated": b1,
        "minority_report": minority,
        "b1_gates": {name: {"status": g["status"]} for name, g in b1_gates.items()},
    }
    (RUN_DIR / "adjudication.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("GATES:", json.dumps({k: v["status"] for k, v in gates.items()}, ensure_ascii=False, indent=2))
    print("\nREFUSAL (attempted CANDIDATE on failed gates):\n  ", refusal)
    print("\nAS STATED  ->", as_stated["verdict"], "/", as_stated["promotion_recommendation"])
    print("B1 REFORM. ->", b1["verdict"], "/", b1["promotion_recommendation"])
    print("MINORITY   ->", minority["minority_report_id"], "| preservation:", minority["preservation_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
