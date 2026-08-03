# Causal identification audit — FORGE-HEXOSE-GS-20260802

Role: `ef-causal-auditor`. Zero Evidence IDs held — every arrow is a `[PRIOR]` candidate from domain physiology, admissible for structuring and design only, **not sealable as a mechanism-graph** until evidence roles bind IDs or mark edges `assumption`.

Estimands tracked separately because they diverge:
- **Q_leaf** = effect of whole-leaf dawn hexose on morning gs.
- **Q_gc** = effect of guard-cell/apoplastic hexose via guard-cell sensing — **the product owner's actual claim**.

## THE CRUX
**Previous-night air temperature is a common cause of the exposure and of at least six other direct determinants of morning gs**: root hydraulic conductance (via root-zone temperature → aquaporin), circadian phase, dawn leaf temperature, photosynthetic induction state, guard-cell starch, and morning VPD. That yields **seven distinct backdoor paths**, and night temperature is itself confounded by sky condition (clear sky → both good prior-day light *and* radiative cooling).

On naturally varying nights, cool night / high dawn hexose / low root hydraulic conductance / shifted clock phase / cold dawn leaf / altered morning VPD **all move together in lockstep by construction**. This is not residual confounding to be adjusted away — it is a design in which the exposure carries no independent variation. *Any hexose coefficient estimated from such data is a relabelled night-temperature coefficient.*

## Identification status
| Design | Q_leaf | Q_gc |
|---|---|---|
| (a) observational, naturally varying nights (**the product owner's situation**) | **NOT_IDENTIFIED** | **NOT_IDENTIFIED** |
| (b) observational + measured covariates | ASSUMPTION_DEPENDENT, and NOT_IDENTIFIED whenever the positivity check fails | **NOT_IDENTIFIED** |
| (c) randomised night temperature | effect of *night temperature* is **IDENTIFIED**; effect of *hexose* is **NOT_IDENTIFIED** | NOT_IDENTIFIED |
| (d) direct sugar manipulation at constant night T | ASSUMPTION_DEPENDENT | **IDENTIFIED** only via inducible **guard-cell-specific** perturbation |
| (e) mediation (c)+(d) | controlled direct effect + erasure test **IDENTIFIED** | "proportion mediated" (NIE/NDE) **NOT_IDENTIFIED** |

(a) is `NOT_IDENTIFIED` rather than `ASSUMPTION_DEPENDENT` because the required exclusion restriction — "night temperature affects morning gs *only* through dawn hexose" — is **contradicted by established physiology**, not merely untested.

(c) is the most commonly overclaimed cell: randomising night temperature makes it a **randomised but invalid instrument** for hexose. You learn cleanly that cool nights lower morning gs; you learn nothing about why.

(e): reporting "X% of the cool-night effect runs through hexose" is an overclaim — `LPR`, `CIRC`, `GC_STARCH`, `TLEAF_DAWN` are mediator–outcome confounders **themselves affected by the exposure**, violating the cross-world condition regardless of randomisation. Report the controlled direct effect and the erasure test instead.

## Four findings the run must carry
1. **The claim's own sign is undetermined.** `TAIR_N → STARCH_DEG → HEX_LEAF` (cool → slower mobilisation → *less* dawn hexose) directly opposes the claimed `TAIR_N → GROWTH_STRUCT → HEX_LEAF` (cool → less structural conversion → *more* hexose). Whether a cool night raises dawn hexose **at all** is an empirical precondition, not a premise.
2. **The effect of interest has an internally opposed sign.** Sugar as osmoticum (`HEX_GC → OSM_GC → GS_AM`, positive) vs sugar as signal (`HEX_GC → ABA → GS_AM`, negative). "Hexose suppresses opening" is a **compartment-specific** claim, not a sugar claim.
3. **Proxy, not exposure.** Whole-leaf hexose is dominated by mesophyll vacuolar pools; the claim is about guard-cell/apoplastic hexose. Measurement class = **PROXY** (association permitted, mechanism/causal ceiling). Worse, the proxy error is almost certainly **differential with respect to night temperature**, so the bias is *not* attenuation-toward-null and is *not* correctable by adjustment. This defeats Q_gc on its own.
4. **The standard analysis error.** Adjusting for A, Ci, E, leaf temperature, or morning Ψ "to control for photosynthesis/water status" conditions on **descendants of gs** and **manufactures** an association where none exists. Pre-register this as a prohibition.

## Most dangerous rivals
- **R1 root-hydraulic** (`TAIR_N → TROOT → LPR → PSI_LEAF → GS_AM`): reproduces *every* observation of design (a) with **no sugar effect whatsoever**. Largest rival.
- **R4 guard-cell starch** (`TAIR_N → GC_STARCH → OSM_GC → GS_AM`): a carbohydrate mechanism a whole-leaf hexose assay would **misattribute to hexose** — i.e. it would be reported as confirmation.
- **R5 mesophyll feedback** (`HEX_LEAF → sugar repression of photosynthesis → A ↓ → Ci ↑ → gs ↓`): hexose really does lower gs, but **not** by guard-cell sensing — directionally right, mechanistically wrong, and it breaks any guard-cell-targeted intervention.
- **R2 circadian**, **R3 thermal/induction**, **R6 reverse causation** (stomata open in *anticipation* of dawn under clock control, so a sugar sample taken after anticipatory opening is a **descendant of the outcome**), **R7 sky** (clear-sky nights are exactly the cool ones).

## Adjustment set — exists on paper, fails in practice
`Z_min` (blocks the backdoors under the primary DAG): night **air** temperature trajectory (hourly, not nightly mean); **root-zone temperature trajectory measured separately**; previous-day DLI + diffuse fraction; sink demand (fruit load / expansion rate); plant identity + season/age; substrate water, irrigation timing, EC; morning boundary conditions at the measurement instant (PPFD at leaf, VPD, CO₂, air T).

**Never adjust for** A, Ci, transpiration, leaf temperature during gas exchange, predawn or morning Ψ_leaf, ABA, guard-cell osmotica, any post-dawn sugar — descendants of gs, colliders, or mediators.

**Defeaters that break `Z_min` anyway:** U1 organ-level actual thermal history (guard-cell and root-tip temperature; sensors report air/substrate at points — confounder measurement error leaves residual confounding of **unbounded** magnitude); U2 multi-day circadian entrainment phase (last night's temperature does not close it); U3 previous-day transpiration-stream apoplastic sugar delivery; and **positivity failure** — conditional on `Z_min`, the residual variance of dawn hexose on "otherwise-equivalent clear days" is near zero, so there is no contrast to estimate. **Pre-register the positivity check as the gate: regress dawn hexose on `Z_min` and inspect overlap by night-temperature stratum; if empty, declare NOT_IDENTIFIED and stop.**

## Decisive experiment
**2 × 2 factorial crossover with split root/shoot thermal control.**
- **Factor A — night thermal treatment applied to canopy air only**, with **root-zone temperature thermostatted constant and identical in all arms**. This *removes* rival R1 by design instead of adjusting for it afterwards.
- **Factor B — dawn guard-cell hexose availability**, set independently of A. Preferred: **block the sensor, not the sugar** — inducible guard-cell-specific knockdown of hexose sensing/uptake, induced after leaf maturity, with inducer-only and null-sibling controls (cleaner than clamping the metabolite because it does not perturb whole-leaf osmotic status). Fallback: pre-dawn apoplastic clamp with matched-osmolality (mannitol) and non-metabolisable-analogue (3-O-methylglucose, 2-deoxyglucose) arms.
- **Rival-positive control arm (essential): cool roots + mild air** — measures the magnitude of R1 rather than merely blocking it. Without it a null in the hexose arm cannot be distinguished from "the cool-night effect was small that night."
- **Pre-registered falsifier (effect erasure):** if clamping dawn guard-cell hexose to mild-night levels abolishes the cool-night suppression of morning gs → mechanism supported. If the suppression persists undiminished → **hexose claim rejected, regardless of how strong the observational correlation was.**

**Measurement requirements**
- **Compartment-resolved sugar**: whole-leaf hexose/sucrose/starch; **epidermal-peel / guard-cell-enriched fraction separately from mesophyll**; **apoplastic washing fluid with a cytosolic-contamination marker reported alongside** (an apoplastic number without the marker is not evidence); **guard-cell starch imaging** (else R4 is indistinguishable from the claim); ideally a guard-cell FRET glucose/sucrose sensor to read the actual exposure instead of a proxy.
- **Timing**: dusk, mid-night, **−60 and −10 min pre-dawn** (darkness, green safelight, flash-freeze in ~5 s, report freeze latency), then +15/+30/+60/+120 min. Only pre-dawn samples may serve as exposures. **Prove from continuous gas exchange that the pre-dawn sample precedes anticipatory opening** — stomata open before light under clock control.
- **gs kinetics, not a spot reading** — this is what separates the rivals: guard-cell sensing → altered initial aperture *and* τ; hydraulic (R1) → a lag that **resolves in 1–2 h**; circadian (R2) → **phase shift with preserved amplitude**; mesophyll (R5) → gs tracks A at unchanged Ci setpoint. A single mid-morning gs cannot distinguish any of these.
- **Matched at measurement**: light-onset ramp, VPD, CO₂, and **actively matched leaf temperature** (else the cool-night arm is just a colder leaf).
- **Unit of replication = chamber** (≥3–4 per arm; plants within a chamber are subsamples). Crossover ≥3 cycles with ≥3-night washout (thermal history entrains over days), Latin square over chambers × cycles, measurement order rotated, assays blinded, **powered on the interaction term** (~4× the n for a main effect).
- **Manipulation check is non-negotiable**: without compartment-resolved proof the clamp moved guard-cell-accessible hexose, a null is *inconclusive*, not a refutation.

## Honest ceiling on observational data
> On clear days in this crop and house, lower morning stomatal conductance is **associated** with cooler preceding nights and with higher pre-dawn whole-leaf hexose. The direction and timing are **consistent with** guard-cell sugar sensing restraining opening. The observation does **not** establish that hexose causes the reduction. At least one equally consistent structure (root-zone cooling → reduced aquaporin-mediated hydraulic conductance) reproduces the entire observed pattern with no causal role for sugar.

| Passport field | Value |
|---|---|
| claim-type ceiling | **association** (not causal, not established mechanism) |
| causal_status | **NOT_IDENTIFIED** |
| epistemic_status | **UNDERDETERMINED** |
| measurement compatibility (whole-leaf → guard-cell hexose) | **PROXY** |
| promotion ceiling | **CANDIDATE** (never EMPIRICALLY_TESTED on observational data) |

**Promotions refused**: "residual hexose suppresses morning stomatal opening" as causal; "cool nights lower morning gs *because of* hexose"; any dose-response or night-temperature setpoint recommendation (a control action is a `do()` claim); any presentation of dawn leaf sugar as a *mechanistic* predictive sensor — under R1/R7 it predicts by proxying night temperature and **will fail the moment the temperature–sugar coupling breaks** (warm cloudy night, chilled-root event, fruit-load change).

## Decision-relevant separation (the practically useful finding)
The estimand needed for the **control decision** and the estimand needed for the **mechanistic claim** are different and differ enormously in cost. Design (c) — randomised night temperature, ~3 chambers × 3 cycles — cheaply and cleanly identifies "night temperature causes morning gs differences," which is **sufficient to set a night-temperature setpoint**. The hexose mechanism requires (d)/(e), is expensive, and is **not needed for the setpoint decision at all**. It becomes necessary only to *sense* sugar as a control input, to *intervene* on sugar directly, or to transfer the rule to another crop/cultivar/climate where the temperature–sugar coupling differs. **Recommend funding these two objectives separately.**
