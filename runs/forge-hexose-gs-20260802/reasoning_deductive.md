# Deductive proof trace — FORGE-HEXOSE-GS-20260802

Role: `ef-deductivist` (structural analysis only; no literature consulted, no evidence IDs consumed).
Verdict: **CHAIN NOT VALID** — 2 SOUND (both explanatorily empty), 2 UNDERDETERMINED, 5 BROKEN.

## Hypothesis as decomposed
- **C1** Hexose modulates stomatal aperture/conductance.
- **C2** Low night temperature limits growth / structural-carbohydrate conversion.
- **C3** Reduced overnight structural conversion leaves elevated residual leaf hexose at dawn.
- **C4** Elevated dawn hexose causally reduces morning stomatal opening on a clear day.

## P0 — the explanandum is ambiguous (smuggled premise)
"오전에 기공이 덜 열린다" is ambiguous between
(i) **between-morning**: morning of day N vs morning of a matched clear day N′, and
(ii) **within-day**: morning gs < midday gs.
Under (ii) the explanandum is the ordinary photosynthetic-induction pattern and needs no hexose story at all. The whole argument silently assumes (i). **This must be fixed by the product owner before anything is testable.**

## Edge verdicts
| Edge | Claim | Verdict | Core reason |
|---|---|---|---|
| E0 | operational meaning of "덜 열린다" | **UNDERDETERMINED** | slower kinetics (τ) vs lower plateau vs delayed onset vs lower integral — different mechanisms, different rivals. Slower kinetics is the canonical signature of induction limitation, not sugar. |
| E1 | cool night → less structural conversion (C2) | **SOUND** but near-analytic | safe, and therefore carries none of the argument's novelty. |
| **E2** | less structural conversion → elevated dawn leaf hexose (C3) | **BROKEN — weakest link** | fails on 4 independent grounds, below. |
| E2a | organ transfer | BROKEN | structural conversion happens overwhelmingly in **sinks** (fruit, young leaves, root), not in the mature **source leaf** whose gs is measured. For a fully expanded leaf G_leaf ≈ 0, so suppressing it has near-zero leverage. The only route is sink→source feedback on export — an unstated, multi-step mechanism requiring export to be *demand*-limited. |
| E2b | carbon-species transfer | BROKEN | carbon not converted to structure ≠ carbon present **as hexose**. It can remain unmobilized starch, sucrose (the dominant soluble pool and transport species), vacuolar sugar, organic/amino acids, RFOs, or be respired. |
| E2c | stock/flow conflation | BROKEN | the argument treats hexose as an **accumulator** of a nightly budget residual. Hexose is a **fast-turnover flux intermediate**: pool size is set by supply/consumption ratio, not cumulative surplus. Category error, independent of any empirical fact. |
| E2d | net sign not entailed | BROKEN | cold slows **both** consumption (respiration Q10≈2, growth, sink demand → raises hexose) **and** supply (starch degradation, phloem loading — active, ATP-dependent → lowers hexose). At dawn the leaf pool is normally at its diel minimum and **supply-driven**; if so, cold **lowers** dawn hexose — the exact opposite of C3. |
| **E3** | C1 → C4 | **BROKEN** | equivocation: "X modulates Y" (existential, unsigned, scope-free) does not entail "elevated X reduces Y" (universal, signed, compartment-specific). Also a sign conflict inside the mechanism space: sugar as **osmoticum** predicts *more* opening; sugar as **signal** (hexokinase) predicts closure. The argument silently commits to signal-dominance at dawn concentrations. |
| E4a | IC2 ∧ IC3 → gs reduced | SOUND but materially empty | formally valid; both antecedents unestablished. |
| **E4b** | observed gs drop → "because hexose" | **BROKEN** | **non-identification**: the putative cause is perfectly collinear with ≥3 rivals sharing the same driver — (i) low root-zone T → aquaporin gating → reduced root hydraulic conductance; (ii) low leaf T → slowed Rubisco activation / induction; (iii) chilling on guard-cell membranes / circadian gating. Not estimable observationally at any sample size. |
| E5 | "same clear day" = comparable | **BROKEN** | "clear" matches the **radiation driver only** — not VPD, leaf/air/root-zone temperature, pre-dawn Ψ_leaf, CO₂, boundary layer, leaf age, fruit load, prior DLI. Cold nights cluster seasonally, so leaf age/load/DLI covary with treatment **by construction**. |
| E6 | bulk-leaf hexose → guard-cell-relevant hexose | **BROKEN** (composition fallacy) | bulk hexose is ~all mesophyll, most likely **vacuolar**; guard cells are a negligible volume fraction with autonomous sugar metabolism. Internal tension: the compartment most likely to accumulate (vacuole) is exactly the one **invisible to cytosolic hexokinase sensing** — and the osmotic fallback has the wrong sign. |
| E7 | dawn state → measured morning window | UNDERDETERMINED | leaf sugar turns over in minutes–hours after light. Also: the apoplastic delivery route (transpiration stream) is **weakest exactly at dawn**, when transpiration ≈ 0 — the mechanism is least available when the hypothesis most needs it. |

## Load-bearing hidden assumptions (22 of 48 flagged ★; the decisive ones)
1. ★ **Thermal asymmetry**: Q10 of hexose *consumption* must exceed Q10 of hexose *production* over the realized night range. This is the necessary-and-sufficient condition for C3's sign and the hypothesis neither states nor derives it.
2. ★ **Window existence**: structural conversion must have a *higher* base temperature than starch degradation + phloem loading, and night N−1 must fall inside that window (below growth threshold, above mobilization collapse). "Cool" is not enough.
3. ★ **Export is sink-demand-limited**, not loading/transport-limited, and the feedback closes within one night.
4. ★ **Hexose, not sucrose**, is the accumulating species; and the increment is **not vacuolar**.
5. ★ **∂aperture/∂[hexose] < 0 monotonically** in the named compartment at realized dawn concentrations, with signalling dominating the osmotic contribution.
6. ★ **Root-zone temperature and root hydraulic conductance are matched** between the compared mornings. This rival alone predicts the entire observation.
7. ★ **Closed-loop problem**: gs → A → sugar → gs is a feedback loop, so cross-sectional day-pair correlation cannot orient the arrow. An interventional design is forced.
8. ★ Normalization basis: the mechanism needs **mol L⁻¹ of a specific compartment's water**; per-gFW is confounded by cold-induced RWC changes, per-area by SLA.

## What is distinctive and worth saving
The hypothesis's one structurally novel commitment is that it predicts an **interaction (prior-day light × night temperature)**, not a night-temperature main effect. Pure thermal/hydraulic rivals predict the main effect with **no** interaction. Second distinctive prediction: **cumulative carryover across consecutive cold nights**. These two are the argument's only current claim to non-triviality and should be the centerpiece of any test.

## Minimal repair (each testable)
- **R1 Thermal-asymmetry**: locate the temperature window where growth ≈ 0 but mobilization/export ≥ X% of reference.
- **R2 Closed budget**: paired dusk/pre-dawn profiling of starch, sucrose, hexose, other solubles + night respiration by gas exchange; export by difference. Hexose increment must be a *stated fraction* of a closed budget, not the residual of unmeasured terms.
- **R3 Locus (sharpest, no temperature needed)**: manipulate **fruit/sink load at constant warm night temperature**. If sink removal reproduces both the dawn hexose rise and the morning gs depression with no temperature change, the sink route is supported and temperature is shown to act *through* sinks — cleanly separating the mechanism from every thermal rival.
- **R4 Compartment**: apoplastic washing fluid + non-aqueous fractionation (cytosol/vacuole/plastid) + guard-cell-targeted reporters.
- **R5 Signed dose-response**: epidermal-peel/isolated-stomata dose-response, glucose vs sucrose vs **equi-osmotic non-metabolizable control** (mannitol, 3-O-methylglucose) at physiological concentrations.
- **R6 Operational definition**: pre-register ONE statistic (integrated gs over sunrise+3h, or plateau gs, or opening τ).
- **R7 Identification**: night-only chilling with the **morning environment clamped identical** and root-zone temperature held constant independently of air temperature.
- **R8 Mediation sufficiency + necessity**: overnight petiole hexose feeding at warm night T (+ non-metabolizable analogue control); and at cold night T, suppress the hexose rise (lower prior-day DLI / longer night / added sink demand) and test whether the gs depression disappears.
- **R9/R10**: formal mediation with no residual direct path; and **quantitative closure** — predicted gs drop from measured hexose × independent dose-response must match the observed drop.

## Falsifiers (cheapest and sharpest first)
- **F1 (decisive, cheap)**: the gs depression appears with equal magnitude after cold nights that followed a **low-light** day. The hypothesis requires the light×temperature interaction; a pure main effect refutes it.
- **F2**: pre-dawn hexose not elevated (or lower) on matched cold-night/bright-prior-day mornings → C3 falsified.
- **F3 (diagnostic pair)**: pre-dawn **starch elevated** while hexose unchanged/lower → carbon backed up as starch, "supply slowed" branch wins. The hypothesis specifically requires *starch fully mobilized* **and** *hexose elevated*. Measure both or the test is worthless.
- **F5**: the hexose increment is entirely **vacuolar** (non-aqueous fractionation) → signalling route decoupled, osmotic fallback has the wrong sign.
- **F6**: glucose at the measured dawn concentration produces no aperture reduction — or an increase → C4 falsified.
- **F7/F8**: overnight hexose feeding at warm night T fails to depress morning gs → no sufficiency; clamping root-zone T and morning VPD abolishes the difference → effect was thermal/hydraulic.
- **F10**: consecutive cold nights fail to raise dawn hexose / depress gs progressively → inconsistent with an accumulating-surplus mechanism.
- **F11**: quantitative closure fails by an order of magnitude even if every qualitative step holds.

## Non-diagnostic observations (tempting, worthless)
- **N1** "morning gs is lower after a cold night" — the originating observation. Predicted by ≥5 rivals **and by both the elevated- and depleted-hexose dawn states**. Zero discriminating power alone.
- **N2** mid-morning sugar↔gs correlation — confounded by the gs→A→sugar loop (reverse causation). Sampling must be pre-dawn.
- **N3** elevated *total soluble sugars* unresolved into glucose/fructose/sucrose — does not test the hexose-specific claim.
- **N6** exogenous sugar closing stomata at **supraphysiological** concentration — scope mismatch; establishes only C1, which is already granted.
- **N7** showing growth was reduced on the cold night — confirms C2 only, which is near-analytic.
- **N11** "stomata are less open in the morning than at midday" — the ordinary induction pattern under the within-day reading of P0.

## Role-declared abstentions
No literature consulted (structural analysis only); no artifact written to `artifacts/reason/deductive/**` per task instruction, so no input/output hash was fabricated; causal identification quantification deferred to `ef-causal-auditor`; the weakest-link determination (E2 over E3) is flagged as a judgment call warranting independent review.
