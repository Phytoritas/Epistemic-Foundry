# Abductive mediation — FORGE-HEXOSE-GS-20260802

Role: `ef-abductive-mediator`. 42 grounded claims consumed; independently re-verified 6 load-bearing spans (6/6 byte-exact). No files written by the role.

## EXPLANANDUM — there is a THIRD reading, and it is probably the right one
| Reading | Statistic | Live rivals | Dead rivals |
|---|---|---|---|
| (i) between-morning | plateau gs or 0–3 h integral at matched clock time | all 13 | — |
| (ii) within-day (morning < midday) | gs(morning) − gs(midday) | ALIGN, DEP, CIRC, COOLLEAF | **H-HEX is actively contradicted here** |
| **(iii) hybrid — likely what the grower means**: the morning→midday *gap* is larger on cool-night days, i.e. gs takes **longer to get where it always gets** | **τ (time to half-max) and time-to-convergence**, referenced to **effective light onset at the crop**, not clock time | **kinetic cluster**: DEP, HYD, COOLLEAF, ALIGN, (weakly) CIRC | **setpoint cluster excluded by construction**: **HEX**, ABA, SINK, PHOTO, DEV |

Under reading (ii) the corpus points the *other* way: sugar-driven closure is scoped to the **afternoon / high-assimilation** phase ("Suc accumulates during the afternoon … up until a certain concentration, after which stomatal closure is induced"; "sucrose … a negative regulator of stomatal opening in periods of high photosynthetic rate"; cotransporters "most highly expressed … such as midday"). **Dawn is the opposite phase.**
Precondition nobody stated: "morning" must be referenced to **effective light onset**, not a clock — stomatal responses "are generally slower than photosynthetic responses", so fixed-clock sampling lands at a different point on the induction curve whenever onset shifts.

## RANKED CANDIDATE EXPLANATIONS (posterior given *this* corpus)
1. **H-ALIGN — measurement/expectation artifact.** Models "consistently overestimated gsw in the morning" under "low VPD (< 0.6 kPa) and low irradiance (< 500 μmol m⁻² s⁻¹)" — exactly a cool clear morning. Plus: growers infer opening from **E** (gutter/drain/sap-flow), and E ∝ gs × VPD, so low morning VPD gives low E at unchanged gs; plus clock-vs-onset misalignment. **Outranks the hypothesis on parsimony: a clear sky causes the good prior-day light AND the radiative cooling AND the low-VPD/low-PPFD morning — so H-ALIGN manufactures the owner's exact interaction with no plant mechanism at all.**
2. **H-SINK — sink-demand carbon economics with no sugar mediator.** The corpus contains a near-exact greenhouse analogue in which the gs effect is present and **the mediator is absent**: cucumber fruit removal → "a decrease in the rate of transpiration, indicating a higher stomatal resistance", while "Neither starch nor mono- and disaccharides accumulated in the morning by lowering the sink demand" (sampled end-of-night). Fruit temperature sets sink activity directly (27.5→17.5 °C decreased fruit growth rate within one day). Optimality supplies the sign ("small η implies demand for NSCs is low, so stomata should close"). **This is a true interaction and needs no hexose step.**
3. **H-HYD / H-COOLLEAF — acute thermal-hydraulic.** Thin corpus support (2 claims) but structurally strong; **uniquely cheap to break in a greenhouse** because the actuator (grow pipe) already exists.
4. **H-DEP — dawn guard-cell sugar/starch DEPLETION (opposite-sign sugar story).** Largest, most direct block in the corpus (τ +40 min in amy3bam1; "half as much Glc as the WT" already in darkness; STP1/STP4 import "essential"; TOR/starvation impairs GC starch degradation and opening; fingerprint = lower gs **with decreased Ci**). Cool dawn slows ATP-dependent mobilization → less GC glucose → higher τ. **Its discriminating value is inverted conditioning: it predicts the deficit is WORSE after DIM days** — the opposite of the owner's interaction.
5. **H-PRED** predawn/nocturnal conductance carry-over · 6. **H-CIRC** circadian phase shift (whole curve translated, amplitude preserved; needs several nights to entrain) · 7. **H-DEV** leaf-cohort/anatomy season confound (cold-developed leaves "twice as thick … higher stomatal cell densities") · 8. **H-PHOTO** next-day photosynthetic capacity · 9. **H-ABA** · 10. **H-OSM** sugar as apoplastic osmoticum · **11. H-HEX (the owner's)** · 12. H-VPD-plant (**corpus predicts the opposite sign**; near-refuted).

**Free triage from the grower's own climate log — the night-temperature band map:**
| Night Tmin | Corpus statement | Rivals activated |
|---|---|---|
| ≥ ~14 °C | growth reduced via SLA/hormones, **photosynthesis intact** | ALIGN, SINK, PRED, CIRC, DEP, HYD |
| 12–14 °C | "75% production level obtained at a night temperature of 12 °C" → TOpt1_Inst 14 °C; no carbohydrate flow below TBase | + SINK strongly |
| < 12 °C | "no growth occurs below 12 °C" | + ABA, DEV |
| < 10 °C | next-day leaf photosynthesis reduced | + **PHOTO** |

**H-HEX's three simultaneous scope mismatches**: (1) physiological apoplastic sugar is **0.4–5.5 mM = the range where sugar OPENS stomata**; closure needed ~100 mM and was reproduced by **mannitol**; (2) wrong time of day (closure is an afternoon/carbon-saturated phenomenon); (3) sensor evidence is overexpression-only and one direct test **excluded** hexokinase from the sugar-opening response. Its one genuine asset: it predicts the light×temperature interaction.
**New non-diagnostic finding (N12): measuring ABA cannot separate H-ABA from H-HEX**, because this corpus makes ABA the *mediator* of hexokinase closure.

## DISCRIMINATING TESTS (ordered by information gain per euro)
| # | Test | Separates | Cost |
|---|---|---|---|
| **T0** | retrospective climate-log audit: prior-day DLI × night Tmin × morning VPD × morning PAR | does the observation exist; reads the night-T band; exposes the VPD/PAR confound | **€0** |
| **T1** | leaf-level PPFD + leaf T + VPD at the instant; re-plot gs vs **time since effective light onset** | **ALIGN vs all plant rivals** | ~€150 |
| **T2** | predawn gs, 30 min before onset (green safelight) | inherited (PRED, CIRC) vs generated at dawn (DEP, HEX, HYD, SINK) | 1 reading |
| **T3** | gs time course predawn→+3 h at 15 min, 6 leaves; report **τ and plateau separately** | kinetic vs setpoint vs translation clusters | porometer rental |
| **T4** | **root-zone-only warming on a cool night** (grow pipe on, air setpoint unchanged) + reciprocal arm | **HYD vs everything canopy-air-driven** — executes the split root/shoot design **at near-zero capital cost because the greenhouse already has the actuator** | ~€60 |
| **T5** | **shade one bay to ~50 % for one clear day**, compare next mornings within the same night | **interaction (HEX, SINK) vs main effect vs inverted (DEP)** — this is falsifier F1, and shading **breaks the sky confound that cloud-based contrasts cannot** | ~€50 |
| **T6** | fruit-load contrast at **constant warm night T**, dawn **starch AND hexose** assayed together | **SINK vs HEX** — the decisive mediator test; replicates the gs-effect-without-sugar pattern | ~€400 |
| **T7** | insert one warm night after ≥3 cool nights; track ≥4 consecutive cool nights | DEV (no recovery) vs CIRC (lagged) vs acute (full recovery); delivers the cumulative-carryover falsifier | one night's heat |
| **T8** | **Ci** at the morning measurement (needs an IRGA that reports Ci — LI-600 does **not**) | stomatal limitation (Ci ↓) vs mesophyll/PHOTO (Ci flat/↑) | instrument access |
| **T9** | dawn compartment sign test: epidermal peel vs whole leaf, glucose+fructose+sucrose+**starch** | **HEX (hexose ↑, starch depleted) vs DEP (hexose ↓/flat, starch retained)** | ~€40/sample |
| **T10** | low-mM dawn sugar feed **with an equi-osmolar mannitol arm** | DEP (rescue) vs HEX (worsen/null) vs OSM (mannitol matches) — **without the mannitol arm any inhibition is uninterpretable** | ~€200 |
| **T11** | **leaf-temperature matching at the instant of measurement** | COOLLEAF vs all — **mandatory control on T2–T10** | ~€0 |

**Explicitly NOT recommended:** ABA quantification (cannot separate ABA from HEX); total-soluble-sugar assays without glucose/fructose/sucrose resolution; any ≥100 mM sugar bioassay; mid-morning sugar↔gs correlation (gs→A→sugar loop).
**Clarification on the analysis prohibition:** never put Ci/A/E/leaf-T/Ψ on the right-hand side of a gs regression (they are descendants of gs) — but using **Ci as a limitation diagnostic** (T8) is a different operation and is legitimate.

## DECISION TREE (one season, one house, no molecular lab before Node 7)
- **Node 0 (T1)** — does the deficit survive re-expression on the physiological time axis at matched leaf PPFD/T/VPD? **No → H-ALIGN explains it; all plant rivals excluded; STOP and re-baseline the expectation.** No consistent difference over ≥6 matched pairs → recall-driven; STOP.
- **Node 1 (T2)** — predawn gs already lower? Yes → inherited (PRED/CIRC in; **DEP and HEX strongly demoted**, both dawn-light-triggered). No → PRED excluded; deficit generated after light onset.
- **Node 2 (T3)** — curve shape: (a) **τ up, plateau equal by +2 h** → **setpoint cluster excluded: HEX, ABA, SINK, PHOTO, DEV**; remaining DEP/HYD/COOLLEAF (this is the amy3bam1 signature). (b) **plateau depressed, still depressed at midday** → DEP/HYD demoted; **HEX, SINK, ABA, PHOTO, DEV remain**. (c) **whole curve translated, τ and plateau preserved** → CIRC.
- **Node 3 (T4)** — root-zone-only warming: deficit abolished → **HYD dominant; STOP for the control decision — set a root-zone/grow-pipe minimum, not an air minimum.**
- **Node 4 (T5)** — shading: interaction only after bright day → main-effect rivals excluded, {HEX, SINK, OSM} remain. **Equal after dim day → H-HEX REFUTED.** Worse after dim day → **DEP favoured, HEX and SINK excluded.**
- **Node 5 (T8)** Ci · **Node 6 (T7)** warm-night insertion + consecutive-night deepening · **Node 7 (T6)** fruit load at constant warm night T: **deficit reproduced with dawn hexose NOT elevated → SINK confirmed, HEX excluded as mediator** · **Node 8 (T9+T10)** compartment sign test then low-mM feed with mannitol; only route to supporting HEX, and the ceiling stays **association** until an inducible guard-cell-specific perturbation is run.

**Budget: ~70 % of the rival set eliminated for under €400 and no lab.** (Nodes 0–2 ≈ €250 + 20 h; Nodes 3–6 ≈ €150; Node 7 ≈ €400; Node 8 only if the sugar branch survives, ≈ €1,500.)

## HIGHEST-INFORMATION-GAIN FIRST MEASUREMENT
> **A paired-morning gs time course — from 30 min before effective light onset to +3 h, at 15-min intervals, on 6 tagged leaves at one canopy position — with leaf-level PPFD, leaf temperature and air VPD logged at the same instant. Select the morning pairs from the existing climate log: matched on prior-day DLI, contrasted on night minimum temperature.**

~€250 (mostly recoverable), ~2.5 h per morning, 6–8 mornings. It executes Nodes 0–2 in one instrument-morning: tests whether the explanandum survives at all, resolves reading (i)/(ii)/(iii), partitions all 13 rivals into three disjoint clusters by curve shape, and supplies the pre-registered statistic every downstream test needs. The free log audit is cheaper but strictly weaker — it cannot see the predawn baseline, cannot separate τ from plateau, and **cannot distinguish a real gs difference from the E/VPD artifact** because the grower's logged proxy is itself E-based.

| Outcome | Meaning | Excluded | Next |
|---|---|---|---|
| **O1** difference vanishes on the physiological time axis | alignment artifact | **all plant rivals** | STOP; re-baseline expectation, do not change night temperature |
| **O2** predawn already lower; curve translated; τ/plateau preserved | circadian/inherited | DEP, **HEX**, PHOTO | T7 (multi-night entrainment) |
| **O3** predawn matched; **τ up tens of min; plateau equal by +1.5–2 h** | kinetic — the guard-cell-starch-mobilization fingerprint | **HEX, ABA, SINK, PHOTO, DEV** | T4. *Note: the surviving sugar story has the **opposite sign** — mornings short of guard-cell hexose, not overloaded* |
| **O4** predawn matched; τ normal; **plateau depressed through midday** | setpoint — **the only outcome keeping the owner's hypothesis in first-tier contention** | DEP, HYD, ALIGN | T5 (interaction sign) + T8 (Ci), then T6 |
| **O5** no consistent difference over ≥6 pairs | selection/recall driven (cool nights are memorable) | everything | STOP; report honestly |

**Two design constraints that make or break it:** (1) **match leaf temperature at the instant of reading**, else the cool-night arm is just a colder leaf and O3 is guaranteed for the wrong reason; (2) **get the bright-day contrast from shading, not from cloud** — cloudy days are also warmer nights, which re-creates the exact sky confound the test exists to break.

## Declared abstentions
Role holds `artifact.read` only, **not** `search.read` → no new corpus spans minted; consequently H-ALIGN's E-vs-gs and dew/onset channels, H-SKY entirely, and H-DEP's temperature→mobilization step rest on **ungrounded priors** and should be routed to `ef-evidence-scout`/`ef-prosecutor` before being bound. No causal or promotion claim made (the NOT_IDENTIFIED / CANDIDATE ceiling stands). `output_hash` refused rather than fabricated (message-only execution mode, same class as the run's SPEC_GAP). Judgment calls flagged: ranking H-ALIGN first is a **parsimony** argument, not an evidential one; the species-scope discount applied to the cabbage and multi-day-cold studies materially affects H-HEX's rank and should be re-weighted by the scope auditor.
