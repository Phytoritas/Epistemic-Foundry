# Method audit — FORGE-HEXOSE-GS-20260802 · **PARTIAL VETO**

Role: `ef-method-auditor` (veto authority). Read-only; methods verified directly in `236, 438, 146, 925, 874, 1027, 1106, 1187, 1278, 192`. No artifact persisted (task forbade writes) → unsealed.

## ASSAY_VALIDITY_EXPOSURE — the exposure is measured nowhere
**Compartment**: exactly one document resolves the apoplast (`236`, dilution-corrected wash with indigo carmine + GC-MS/MS) — and its contamination control is **argued by citation, not measured** (no cytosolic marker reported alongside). `438` gives the only true guard-cell sugar measurement (guard-cell-enriched peels), but in Arabidopsis, mutant-vs-WT, **30 min after illumination** — not a dawn exposure. Everything else is whole-tissue.

**Hexose specificity**: the single most on-point crop experiment (`1027`) reports **"Mono- and disaccharides" as one pool** — an aggregate that cannot test a hexose-specific claim.

**Sampling phase — disqualifying**:
- `1027` is the only study sampling at the right phase ("at the end of the night period because at that time the carbohydrate contents are less variable with time") — and it returned a **null**.
- `146` samples **2–5 h into the photoperiod**; its glucose-decline result therefore cannot speak to dawn hexose at all (it is a descendant of that morning's gs).
- `925`/`874` **do not report time of day**. For a fast-turnover flux intermediate this makes the measurement uninterpretable for a diel claim.
- **No cited study reports freeze latency, safelight handling or quench time. Zero.**

**Normalization — corrupted by the treatment itself**: every crop measurement is per dry/fresh weight or area, and the treatment moves the denominator in the same direction as the hypothesized effect (`1027` dry-matter content 15.3 → 13.7 % across the very treatments being compared; `146` cold-developed leaves "twice as thick (eight cell layers)"; `1246` SLA falls at low temperature *because of* NSC accumulation). **This is differential measurement error with respect to the exposure — not correctable by adjustment.**

**Coverage gap in the corpus, not just the extraction**: `192_A_New_Mechanism_for_the_Regulation_of_Stomatal_Aperture_Size` (Lu/Outlaw 1997) is **present in the snapshot but was never extracted** — the canonical compartment-resolved intact-leaf measurement, reporting mesophyll-derived sucrose in guard-cell walls sufficient to diminish opening, and identifying **"high transpiration rate"** as the factor that loads guard-cell walls (a primary-measurement instantiation of the dawn-delivery failure). Also uncited: `439_Guard_Cells_Integrate_Light_and_Temperature_Signals`.

## ASSAY_VALIDITY_OUTCOME
Gold-standard instances exist but both point away from the hypothesis: `236` clamps leaf temperature/CO₂/RH on an LI-6800; `438` measures **kinetics** (τ_WT = 17 ± 1 min vs τ_amy3bam1 = 57 ± 7 min) — but normalizes gs to end-of-night, so it **deliberately discards absolute morning gs magnitude** and must not be cited for a plateau claim.
Elsewhere the outcome is **inferred, not measured**: `1027` infers stomatal resistance from a fall in transpiration with no VPD normalization or leaf-temperature correction. `1187`'s "canopy conductance" is the **E/VPD ratio** — which convolves leaf area, boundary layer, hydraulic supply and aperture, so on cool mornings it is **maximally confounded with the leading rival (root hydraulics)** — and it is exactly the measurement a commercial house most naturally produces.
Across all 107 claims: **no** treatment of stomatal patchiness, **no** one-/two-sided convention, **no** boundary-layer correction, **no** cuticular floor. And the explanandum is never operationalized: no cited result is a **between-morning** contrast; the field itself declares this open (`023`: "we need more mechanistic studies … to more accurately determine whether predawn stomatal conductance affects the response time of stomata to illumination in the morning").

## CONCENTRATION_REALISM — the decisive datum
> `236`: "high sucrose concentrations … have been hypothesized to constitute an osmotic feedback mechanism … and **we did observe such inhibition by 100 mM sucrose or mannitol** in gas exchange experiments"; figure legend: "Sucrose (1 mM) **but not 1 mM mannitol** enhances RL-induced stomatal conductance increases …; **higher concentrations of both solutes inhibit** conductance increases below control levels."

1. **An osmotic control reproduced the closure effect.** Mannitol is not transported, not phosphorylated, not a hexose. Closure at 100 mM is an osmotic response — the closure signal carries **no information about sugar sensing**.
2. **The concentration is unreal**: reported apoplastic sucrose is **0.4–5.5 mM**; 100 mM is **18–250×** physiological.
3. **At physiological concentration the sign is the opposite** — low-mM sucrose, fructose, glucose and sorbose **promote** opening.
4. **Hexokinase was actively excluded** in the one experiment that tested it (NAG inhibition *and* HXK overexpression left the sugar-opening response unchanged).
5. The review carrying the strongest pro-closure statement (`432`) contains **zero occurrences of mannitol, sorbitol, osmoticum or "metabolically inactive"** — no osmotic control is reported at all.
6. **Non-metabolizable analogues appear in 2 of 1,281 corpus documents**, neither a guard-cell study → **sensing cannot be separated from metabolism anywhere in the available evidence**.

## DESIGN_STRENGTH_BY_LINK
| Link | Best evidence class | Sign at relevant concentration/compartment |
|---|---|---|
| **C1** | randomized intervention + genetic perturbation with proper controls (`236`, `438`, `263`, `437`, `806`) | **positive** (sugar promotes/enables opening) at 0.4–5.5 mM in the guard cell; negative only at 100 mM where mannitol reproduces it |
| **C2** | randomized intervention (`1027` fruit-cuvette 27.5→17.5 °C) + model (`857`) | negative (cool → less sink growth) — but about **sinks**, not the measured source leaf; countered by `1256` (partitioning "not significantly affected by temperature directly over 18–24 °C") |
| **C3** | observational / whole-tissue, wrong species, phase or stress range | **contradicted more often than supported**; the one pre-dawn-sampled experiment is a null |
| **C4** | **modeling output + one 1979 background assertion** | **zero direct measurements support C4**; 27 of 38 C4 claims contradict |

**Reviews doing measurement's work (flagged)**: the *only* affirmative C3 statement in the entire run is one review sentence ("low night temperatures increase soluble sugars and starch content…", no compartment, no time of day, "soluble sugars" unresolved). The best conceptual pro-hypothesis result (guard-cell-specific HXK overexpression) reaches this run **only as a review body sentence**; the primary paper was never extracted, so n, controls and promoter specificity are unknown. All 12 claims from `1106` are review layer (it is a *New Phytologist* **Tansley insight**, not a primary study).

## STATISTICAL_ADEQUACY — inadequate at every level
```
effect_size populated:  0 / 107
sample_size populated:  0 / 107
p_value populated:      1 / 107
all four quantitative fields null: 71 / 107
```
No confidence interval appears anywhere. Reported n in the primary sources is **3**, with uncorrected pairwise t-tests across a multi-concentration panel (`236`). The pivotal C3 null (`1027`) has **SE 30–80 % of the mean** (mono/disaccharides 29.4, 13.2, 26.4, 22.3, 31.1 mg g⁻¹, se 10.6) — it could not have detected a doubling: absence of evidence, not evidence of absence, but equally not support. The only surviving p-value is a linear trend under **sustained 5 °C over 45 days**, sampled 2–5 h into the photoperiod, in the direction opposite to C3.
**Pseudoreplication and chamber–treatment confounding are universal**: in every temperature experiment, treatment level is confounded with chamber/compartment/period → **effective n = 1 per level**. The causal audit's requirement (chamber as unit, ≥3–4 per arm) is met by **zero** studies.
**Stressor-range mismatch**: crop temperature × hexose experiments ran at 11/−1 °C, 16/4 °C, or 20/16–36/32 °C — none brackets "adequate light, temperature too low for growth but otherwise normal". Sub-zero night air is freezing stress, a different exposure entirely.
**Would any cited quantitative result survive as evidence for a between-morning effect in a production greenhouse? No.** Not one effect size was estimated on a between-morning contrast.

## MEASURABILITY_IN_THE_OWNER'S_SETTING
| Requirement to test C4 | Available in a commercial greenhouse? |
|---|---|
| guard-cell/apoplastic hexose at −60/−10 min pre-dawn | **No** (needs AWF with dilution marker or dissection, green safelight, sub-5-s freeze) |
| glucose/fructose resolved, not "soluble sugars" | off-line only, and only on the **proxy** whole-leaf extract |
| normalization to compartment water | **No** — all achievable bases co-move with night temperature |
| gs **kinetics** (τ, plateau, onset) through dark→light | **No** with a porometer; yet kinetics is the only readout separating guard-cell sensing (τ) / hydraulic (1–2 h lag) / circadian (phase shift) / mesophyll feedback |
| leaf temperature actively matched between mornings | **No** — after a cool night the leaf is simply colder |
| root-zone temperature controlled independently of air | **No** in a normal house — R1 is then not merely unadjusted but unmeasured |
| chamber as unit of replication, ≥3/arm | **No** — a commercial house is one thermal compartment (n = 1) |

**What the owner CAN legitimately do**: (a) **instrument root-zone temperature separately from air** — cheap, and it converts the biggest rival from invisible to measurable; (b) log a **pre-registered** gs statistic on a fixed tagged-leaf cohort at fixed clock offsets from sunrise with leaf IR temperature; (c) test the **prior-day-light × night-temperature interaction** and the **consecutive-cold-night carryover** — no sugar assay needed, and they can falsify the hypothesis cheaply; (d) treat any whole-leaf dawn sugar series as an **association-level covariate only**, never a mechanistic sensor input.

## VETO — PARTIAL
**Blocks promotion of C4 and of the composite hypothesis above `CANDIDATE`** — specifically blocks `EMPIRICALLY_TESTED`, any `mechanism`-typed status, and any causal or dose-response claim. Grounds (measurement/design/statistics, independent of the identification argument):
- **V1** C4's entire affirmative base is 3 modeling claims + 1 background assertion (Lenz 1979); zero direct measurements; 27/38 contradict.
- **V2** the closure effect has a **positive osmotic control** (mannitol reproduces it) → attributable to osmolarity, not the ligand.
- **V3** closure concentration is 18–250× physiological and the sign reverses at physiological dose.
- **V4** sensing cannot be separated from metabolism or osmosis anywhere in this corpus.
- **V5** construct mismatch in the intervention arm: the hypothesis is about **hexose**; the closure evidence is **sucrose and mannitol**. *No experiment shows glucose or fructose at a physiological apoplastic concentration reducing gs.*
- **V6** the statistical substrate cannot support a promotion (0 effect sizes, 0 sample sizes, effective n = 1 per temperature level).

**NOT vetoed**: C1 at association/mechanism-plausible **with the sign stated as concentration- and compartment-dependent**; C2 at intervention-supported **scoped to sink organs** (not the mature source leaf); reporting the night-temperature → morning-gs **association** with rivals named.

**To lift the veto — both arms required:**
- **Arm A**: signed, hexose-specific, concentration-realistic dose–response (glucose and fructose **separately**, 0.4–5.5 mM apoplastic-equivalent, leaf temperature clamped) run **concurrently** with matched-osmolality mannitol/sorbitol **and** a non-metabolizable analogue. Lift condition: hexose produces the effect and **mannitol at matched osmolality does not**. *If mannitol reproduces it again, C4 is refuted at the assay level, not merely unsupported.*
- **Arm B**: paired pre-dawn compartment-resolved exposure (−60/−10 min, green safelight, freeze latency <5 s, glucose/fructose separately in whole leaf + guard-cell-enriched fraction + AWF **with a cytosolic-contamination marker reported alongside**, plus guard-cell starch, normalized to compartment water) with **continuous** gs kinetics through the transition, one **pre-registered** statistic, leaf temperature actively matched, root-zone temperature thermostatted identically, **chamber as unit of replication ≥3–4 per arm**, crossover with ≥3-night washout, blinded assays, and a mandatory manipulation check.

**Cheapest test that could kill it without any sugar assay**: the prior-day-light × night-temperature **interaction** plus consecutive-cold-night carryover. If the depression appears at equal magnitude after cool nights following **low-light** days, the hypothesis's only distinctive structural commitment fails and **the veto becomes permanent for this formulation**.

**Status PARTIAL**: ~20 cited documents' methods were not read directly; `192` and `439` should be routed back to the extractor before re-adjudication (neither would lift the veto on current reading; **`192` strengthens it**).
