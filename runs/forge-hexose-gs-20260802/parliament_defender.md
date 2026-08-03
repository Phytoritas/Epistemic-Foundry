# Defender brief — FORGE-HEXOSE-GS-20260802

Role: `ef-defender`. Read all 107 grounded claims + both reasoning traces + 7 source texts. Declared ACL widening (read `contradicts`/`conditions` claims) authorized by the dispatching task. No files written, no state mutated.

## BOUNDED_CLAIM — the proposal must be split in two

### B1 — the version defensible on the evidence (mediator = carbon/sink status, **not** guard-cell hexose)
> In greenhouse **tomato and cucumber**, on clear days, morning stomatal conductance is reduced after nights whose canopy temperature fell into the band where **structural growth is strongly inhibited but carbon supply is not**, and the proximate mediator is **reduced whole-plant sink demand for assimilate** — not necessarily residual hexose.

Scope: tomato/cucumber greenhouse fruiting crops (the mechanistic sugar literature is *Arabidopsis*/*Vicia faba* and does not transfer as measured); night window **~10–14 °C canopy** (inferred across sources, not quoted): `857` "TOpt1_Inst of 14°C"; `1246` "no growth occurs below 12°C" + "Photosynthesis is not affected by suboptimal night temperature"; `1060` next-day photosynthesis falls when Tmin < 10 °C. Compartment: whole-leaf/whole-plant NSC and export flux. Window: sunrise→+2 h, one pre-registered statistic. Claim type: **association + theory-supported mechanism. Not causal, not identified.**

### B2 — the narrowest survivable form of the owner's *actual* hexose mechanism
> There exists a supra-optimal regime for guard-cell hexose, so ∂aperture/∂[hexose] is not everywhere positive. A bright prior day plus a growth-limiting night would produce a **carbon-replete dawn** — giving guard cells, at dawn, the carbon status the literature only ever assigns to midday. **That is an empty cell in the 2×2 and has never been measured.**

The required concentration band is quantifiable **and empty**: highest apoplastic sugar reported anywhere in the corpus is **5.5 mM** (`236`: "Reported apoplastic sucrose concentrations are 0.4–5.5 mM … matching the range at which we detected enhancement of stomatal opening"); the lowest dose at which any opposition to opening appears is **30 mM**. The claim must live in **5–30 mM, where the corpus has zero measurements**. Status: candidate only, unsupported.

## TWO_REGIME_RECONCILIATION — both literatures can be true simultaneously

| Axis | Opening regime | Closure regime |
|---|---|---|
| Sensor | hexokinase-**independent** (PM H⁺-ATPase ↑, anion currents ↓) | hexokinase → ABA in guard cells |
| Concentration | 0.4–1 mM apoplastic | 30–100 mM applied |
| Compartment | apoplast → guard-cell cytosol | guard-cell symplast (signal); apoplast (osmotic, ≥100 mM) |
| Carbon status | dawn, carbon-**depleted** | midday/afternoon, carbon-**saturated** |

Non-ad-hoc because the corpus supplies a **sensor dissociation**: `236` — "neither treatment with N-acetyl-glucosamine (NAG), a pharmacological inhibitor of hexokinase, nor genetic overexpression of hexokinase impacted sucrose enhancement of the guard-cell red-light response, ruling out a role for hexokinase." Different sensors ⇒ two additive branches, not one contradicted result. `1106` states the split outright: "mesophyll-sugars are required for stomatal opening at dawn and … promote stomatal closure when plants are carbon-saturated."

**Which regime is the owner's scenario in? The OPENING regime — unambiguously, on every axis the corpus can resolve** (time: dawn; concentration: measured in-planta sits inside the enhancement band, 1–2 orders below any closure dose; carbon status: `806` "sugar supply significantly promoted the stomatal opening under certain carbon starvation conditions … Under normal light conditions … exogenous sugar supplementation did not affect stomatal opening" — adding sugar goes positive → zero, **never negative at physiological dose**).

**The one honest opening for the defence:** every corpus source conflates "dawn" with "carbon-depleted". The owner's construction deliberately breaks that conflation (dawn ∧ carbon-replete). `806` shows the positive branch is itself carbon-status-gated, so `438`'s loss-of-function result — obtained at a normally carbon-**depleted** dawn — cannot fix the sign of the derivative at a carbon-**replete** dawn. *That is the entire legitimate defence. It is a claim about an untested cell, not about evidence.*

## STRONGEST_SUPPORT
**Guard-cell-specific hexokinase gain-of-function** — the only intervention in the corpus with the right sign, compartment, sugar class, **and a crop species**:
- `432`: "overexpression of HXK in guard cells using a guard cell–specific promotor … also resulted in reduced stomatal apertures and transpiration rates"
- `537`: "Guard cell-specific expression of hexokinase reduces whole-plant transpiration and increases water-use efficiency (WUE) in **Solanum lycopersicum**."
- `432` mechanism: "hexose monomers that are sensed by hexokinase, and result in stomatal closure via a mechanism mediated by abscisic acid (ABA) produced in the guard cells"; and "higher concentrations of sucrose and the HXK substrates [glucose, fructose, and **mannose**]" — mannose is the diagnostic HXK-signalling agonist, so this is **signalling, not osmotic**.

**Establishes:** guard cells contain a cell-autonomous, hexose-specific, hexokinase-dependent, non-osmotic pathway whose activation reduces aperture and whole-plant transpiration **in tomato**. → *The owner's choice of hexose as the effector species is not a mistake.*
**Does not establish:** any dawn timing (constitutive promoter, whole-day average; `665` scopes it to "long-term coordination … could not account for short-term coordination"); that the **ligand** ever varies physiologically far enough to move the pathway (sensor sufficiency ≠ ligand-driven modulation); any link to night temperature, prior-day light, or residual dawn hexose (**zero**); that HXK dominates when both branches are present (`236` found HXK overexpression did **not** alter the sugar-opening response).

## WHAT_SURVIVES_IF_HEXOSE_FAILS
1. **C2 is the best-supported link in the run and is essentially safe** (`1246` reduced RGR under suboptimal night T with photosynthesis unaffected; `1027` fruit temperature 27.5→17.5 °C decreased fruit growth rate within one day; `857` encodes a temperature-gated carbohydrate buffer outflow).
2. **The prior-day-light × night-temperature INTERACTION is the hypothesis's only structurally novel commitment and survives any mediator.** Every thermal/hydraulic/circadian rival predicts a night-temperature **main effect**; only a carbon-carryover mechanism requires a bright prior day. **No corpus source has tested it.**
3. **The sink-feedback route to gs, directly measured in the owner's crop family at constant temperature** — `1027`: "a substantial reduction in photosynthesis was found only when all fruits were removed. This reduction was accompanied by a decrease in the rate of transpiration, indicating a higher stomatal resistance", under "constant 25 °C day and night". **Sink limitation alone depressed conductance with no temperature change.** Overnight export is demonstrably sink-gated (`1246`: "less transport of starch from leaves at night on root-restricted plants").
4. **Carbon-status framing of morning conductance has independent theoretical backing** (`046` dawn gw as a function of NSC; `073` "Stomatal conductance decreased as leaves accumulated more soluble carbohydrates"; `090` "the accumulation of excess photosynthate drives stomatal closure in the afternoon").
5. **The operational decision survives intact** — a randomised night-temperature design identifies the setpoint effect and does not need the hexose mechanism at all.

> **The observation is real and worth explaining. The proposed mechanism is a different question, and it is currently losing.**

## WEAK_LINKS_I_CANNOT_REPAIR
- **W1** C4 is contradicted by direct measurement at exactly the owner's compartment and time (`438` +40 min opening time constant when guard-cell glucose is lost; `1106` "Glc import to guard cells at dawn via … STP1 and STP4 is essential for … light-induced stomatal opening"). **There is no corpus evidence of hexose closing stomata at dawn at any concentration.**
- **W1b** Within the carbohydrate family the observation does not even select a sign: guard-cell starch is built during the day from mesophyll sucrose, so a bright prior day + consumption-suppressing night should leave **more** dawn guard-cell starch → more glucose → **faster** opening.
- **W2 (the unrepairable quantitative failure)** The concentration gap is **1–2 orders of magnitude**. Measured apoplastic sucrose: 0.36 mM @60 min, 1.9 mM @120 min — inside the *enhancement* band. The only inhibition observed is at 100 mM and is **reproduced by mannitol** (osmotic, not signalling). *A cool night plausibly shifts leaf sugar by tens of percent, not 50–100×. The dose the mechanism needs is not reachable by the perturbation the hypothesis proposes.*
- **W3** C3's sign is not established and the hexose-specific direct measurements mostly run the wrong way (`1027` null at certified end-of-night sampling; `146` glucose proportion falls under cold; `925` fructose significantly lower under cool regimes). The supporting side is review-layer and time-of-day-blind.
- **W4** Where cold does raise hexose, the cause is different and in the wrong compartment (`012` CsVI1 **vacuolar** invertase) — vacuolar hexose is invisible to cytosolic hexokinase, and the osmotic fallback has the wrong sign.
- **W5** The stock/flow category error is not repairable by literature; only a closed overnight carbon budget fixes it.
- **W6** Non-identification stands and the corpus arms the rivals (`046` temperature-dependent hydraulic conductances; `012` low T raises ABA; `1060` next-day photosynthesis; `1187` late-night conductance rise "driven solely by endogenous circadian regulation").
- **W8** `665` explicitly scopes sugar→HXK closure to **long-term** coordination, denying it the timescale the hypothesis needs.
- **W9** The explanandum is ambiguous (between-morning vs within-day) and only the owner can fix it.
- **W10** The chain is assembled **entirely across systems**: every C1/C4 mechanism claim is Arabidopsis/*V. faba* epidermal peels; every C2/C3 crop claim is tomato/cucumber whole-plant. **Not one paper in the corpus measures dawn hexose and morning gs in the same plant** (searched all five candidate crop/nocturnal-conductance documents: 0 matches).

## PROMOTION_REQUESTED — `candidate-with-narrow-scope`, for **B1 only**
| Component | Honest level |
|---|---|
| C2 (cool night limits structural conversion, tomato, <12–14 °C) | `literature-grounded` |
| C1-existence (an opening branch AND a hexokinase closure branch both exist) | `literature-grounded` |
| Two-regime framework | `literature-grounded` as a framework; regime boundary unquantified |
| C3 (cool night raises residual dawn **hexose**) | `candidate`, contested |
| **C4 as stated (dawn hexose suppresses morning opening)** | **no promotion requested; a `reject` on this link is not contested** |
| Overall B1 (carbon/sink-status form) | `candidate-with-narrow-scope` |
| Overall B2 (guard-cell hexose form) | `candidate-with-narrow-scope`, contingent entirely on the untested dawn ∧ carbon-replete cell |

**The single test the defence stakes itself on is not a sugar assay:** does the morning depression also appear after cold nights that followed a **low-light** day? A main effect with no prior-day-light interaction refutes the carbon-carryover family entirely — hexose or otherwise — for the price of one extra treatment arm.

*Caveat recorded by the role: several spans it located (236 apoplastic time-course, 438 guard-cell starch build-up, 046 χw, 090 η passage) are new and not yet in `grounded-claims.json`; they must be re-grounded by the extractor before any downstream role binds them.*
