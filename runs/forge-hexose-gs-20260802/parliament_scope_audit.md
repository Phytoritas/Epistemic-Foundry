# Scope audit — FORGE-HEXOSE-GS-20260802 · **VETO ISSUED**

Role: `ef-scope-auditor` (veto authority). Read-only; no artifact persisted (task forbade writes), so this audit is **unsealed** until the parent persists it.

**Untrusted-input correction:** the dispatching brief called the corpus "tomato, cucumber, sweet pepper, rose"-dominated. Verified against the snapshot: title counts are Tomato 59, Greenhouse 36, Canopy 28, Cucumber 12, Lettuce 13, Strawberry 7, **paprika 1, rose 0** ("rose" hits were the substring in *suc-rose*). Audited against the corpus, not the brief.

## INFERRED_TARGET_SCOPE (declared inference, not a stated fact)
A heated commercial glasshouse growing an **indeterminate fruiting vine crop — tomato and/or cucumber**, controllable night setpoint, gs read on a mature source leaf or inferred at canopy level, clear days.
If the crop is actually pepper/rose → **the veto hardens** (no such physiology in the corpus at all). If leafy/vegetative → the C2→C3 branch loses its premise (it rests on a large reproductive sink). If "morning" is *within-day* → the explanandum is ordinary photosynthetic induction and no transfer is needed.

## SPECIES_GAP — SEVERE
Of 107 claims, 33 are `direct_measurement`; of those **20 are Arabidopsis/*Vicia faba***. Restricting to direct measurements joining **sugar ↔ stomata**: **12 claims, of which 10 are Arabidopsis/*V. faba***, 1 unattributed, and **exactly 1 is in a target crop — A2-024, which is the null-mediator result**.
> **There is no direct measurement of any hexose→stomatal relationship in tomato, cucumber, pepper or rose anywhere in this evidence set.**

The tomato bridge (`432`, `537` guard-cell HXK overexpression) is **review-layer and transgenic**, and is misread if taken as support: it shows that *forcing extra sensing capacity* into tomato guard cells lowers gs. It says nothing about whether **endogenous hexose variation within the wild-type range** modulates tomato gs — a dose *and* genotype mismatch on top of species. Its own framing is "a target for manipulation for crop improvements", i.e. an engineering handle, not wild-type physiology.

Anatomy is explicitly **not** claimed as the barrier (no such comparison exists in the corpus; all four species are kidney-shaped-guard-cell dicots). The real species barrier is the **reproductive sink**: fruit fraction of dry matter **0.53–0.70** in tomato (`1256`) vs no comparable sink in an Arabidopsis rosette.
Within-species moderator: cold→NSC accumulation is **cultivar-dependent** (`1246`: much less pronounced in cold-tolerant wild tomato species) — "tomato" is under-specified; scope to a cultivar.
Counter-species signal: the only crop hexose measurements at low temperature go the **wrong way** (`925` fructose significantly lower under both cool regimes; `874` glucose+fructose highest at 36/32 °C).

## SETTING_GAP — SEVERE, and it is the gap that bites at dawn
From `236` methods (read directly): leaves excised **before lights on**; peels held in buffer **in the dark 1.5–2 h to ensure closure**; petioles immersed in 0/1/100 mM sucrose or mannitol. The assay removes mesophyll, phloem, root and transpiration stream, and **sets apoplastic concentration by fiat**. In an intact dawn leaf that concentration is not a setting — it is the result of flows that are ≈ 0 at that moment.

**The decisive, empirical setting finding:**
> `236`: "RL-induced AF from V. faba **but not AF from leaves kept in darkness** enhances stomatal opening"; "**Sucrose administration did not suffice to cause stomatal opening in darkness**". A1-024: 1 mM sucrose fed through the petiole increased gs "**under red light … but not darkness**".

**In this corpus the apoplastic sugar messenger is light-gated; dark-collected apoplastic fluid is inert.** The hypothesis needs apoplastic/guard-cell hexose to act in the dark-to-dawn window, when transpiration ≈ 0 and there has been no photosynthate loading for 10+ h. The corpus provides **zero evidence that anything happens in that state, and one direct demonstration that it does not.** This upgrades the deductivist's E7 from a structural worry to an **evidenced setting failure**. The mechanism's own authors state the premise conditionally: "Suc moving throughout the apoplast of a **transpiring leaf**" (`537`) — at dawn there is no transpiring leaf.

## SCALE_GAP — SEVERE; contains the single most decision-relevant fact
`1027` (cucumber, Marcelis 1991): fruit number 0/1/3/5/7 with "**The temperature during both day and night was 25 °C**" — sink demand varied with temperature held constant, the cleanest available separation.
- A2-024: "This reduction was accompanied by a decrease in the rate of transpiration, **indicating a higher stomatal resistance**."
- A2-020: "**Neither starch nor mono- and disaccharides accumulated in the morning by lowering the sink demand.**"

> **A scale-level dissociation of the mediator from the outcome, in a target crop, at the target scale, with temperature controlled. If the owner's chain were right, this is precisely the experiment that should have confirmed it — and it separated the two halves instead.**

Honest caveats (both weaken rather than rescue): a conflicting prior exists (`1027` cites Pharr et al. finding cucumber leaf starch rising to ~200 mg g⁻¹ on fruit removal), so the sugar-accumulation step is heterogeneous across studies; and the measured leaf was 35 d past unfolding, past its photosynthetic peak.

Canopy scale is already occupied by a non-sugar driver: `1187` — the late-night rise in **canopy** conductance was "independent of environmental variation and **driven solely by endogenous circadian regulation**". And the crop model the owner's setting is built on has **no leaf-level state variable in which a "residual" could sit** (`857`'s CBuf is a whole-plant buffer).

## TIME_GAP — SEVERE; the corpus explicitly excludes the needed timescale
> `665`: "Although this process may provide long-term coordination …, such a mechanism **could not account for short-term coordination** between photosynthesis and stomatal behavior, as reduced stomatal conductance is not usually observed under conditions of high photosynthetic rates."

Every dawn-specific mechanistic claim has guard-cell hexose **enabling** opening (`1106` "At dawn, rapid degradation of starch releases Glc which promotes efficient and fast stomatal opening"; STP1/STP4 import "essential"; `438` +40 min time constant; "Already in darkness, amy3bam1 guard cells had half as much Glc as the WT" — dawn guard-cell glucose comes from **guard-cell starch, autonomously**, not from leftover mesophyll hexose).

The phase rule is explicit and the hypothesis crosses it: `1106` — "mesophyll-sugars are **required for stomatal opening at dawn** and … they promote stomatal closure **when plants are carbon-saturated**."
> **The hypothesis imports the afternoon sign into the dawn phase.** That is a time-phase sign-transfer error, and the corpus names both phases in one sentence.

Also: the cold→sugar response is a days-timescale transient that **reverses** (`146` glucose "declined steadily from 4 d", P<0.005); crop-scale, "the long-term average temperature rather than the day-night temperature regime determines crop growth and yield" and temperature integration up to 24 days did not influence yield (`1246`); the sink-feedback loop in fruiting cucumber closes over **>16 days**, not overnight.

**One legitimate night→morning carry-over does exist in the corpus — and it is not stomatal:** `1060` (CROPGRO-Tomato) — "a minimum night temperature effect in the model that **reduces the next day's leaf photosynthesis**". The grower's intuition that last night carries into this morning is already represented in crop models, as a **photosynthetic-capacity** term.

## CONSTRUCT_VALIDITY
**1. "구조탄수화물 전환" — operationalizable, and this is the good news.** In `857` it is model bookkeeping with published numbers: `TBase_Inst = 6`, `TOpt1_Inst = 14`, `TBase_24 = 12`, `TOpt1_24 = 18`, `TOpt2_24 = 22` °C; "Below a certain base temperature TBase no carbohydrate flow to organs is expected (h=0), between TOpt1 and TOpt2 the carbon flow is maximal (h=1)". Crucially **temperature does not change the conversion coefficient, it changes the flow** (`1256`: the growth coefficient "is usually thought to be relatively unaffected by temperature on theoretical grounds") — so C2 is a **sink-rate** claim, not an efficiency claim.
> **Operational consequence: in a heated tomato house a "too-cool night" is typically 15–17 °C, which sits on the LINEAR RAMP (partial inhibition), not in the "growth stopped, carbon backs up" regime the hypothesis imagines. The stop regime needs a 24-h mean near 12 °C.**
Caveat: the 14 °C anchor is **extrapolated from a single observation** (Khayat et al. 1985) — thin calibration for a setpoint decision.

**2. "잔류 Hexose" — folk construct, not measurable as stated.** Needs hexose-specificity + stock semantics + a guard-cell-sensible compartment. Every crop-level sugar measurement in the set is **whole-tissue**; the corpus's own crop mechanism for cold-induced hexose (`012` cucumber vacuolar invertase CsVI1) deposits hexose in the **vacuole — the one compartment that cannot reach cytosolic guard-cell hexokinase**; and the stock semantics failed at crop scale (A2-020).

**3. "기공이 덜 열린다" — unoperationalized, and the sub-constructs dissociate**: opening time constant τ (+40 min), extent/plateau, predawn gn, response time to morning illumination (`023` says this is unresolved). Trap: `016` reports coupled models "consistently overestimated morning stomatal conductance under low VPD (below 0.6 kPa) and low irradiance (below 500 µmol m⁻² s⁻¹)" — a grower comparing observed morning gs against an expectation may be observing a **known model bias in exactly the morning regime**, not a plant response.

### WORST CONSTRUCT MISMATCH — the exposure
> **"잔류 Hexose" is a whole-leaf, stock-semantics, compartment-blind construct. Every mechanism in this corpus capable of producing the claimed effect operates on a guard-cell-accessible, flow-determined, light-gated *concentration*. These are not the same variable measured with different precision — they are different variables.** Compounded because the only named crop route for cold-induced hexose routes it **away** from the sensing compartment.

## LOAD / PHENOLOGY
Designs separating load from temperature exist and were run: `1256` (3-week 23/18 °C setpoints × 3 vs 7 fruits/truss) found "**dry matter distribution in tomato is not significantly affected by temperature directly**", with fruit fraction 0.53 vs 0.70 **set by pruning**, independent of mean temperature over 18–24 °C → **over the owner's operating range, fruit load, not temperature, sets partitioning**. `1027` varied fruit number at constant 25 °C.
Phenology confounds: cold-developed leaves are "twice as thick (eight cell layers)" with "higher epidermal and stomatal cell densities" — two "otherwise-equivalent clear mornings" in different parts of a season are measuring **different leaves**.
Missing: **no study crosses night temperature × fruit load × dawn hexose × morning gs.** The owner can separate load from temperature for *partitioning*, but not for *gs*.

## VETO
**`VETO: guard-cell-hexose → morning-gs mechanism, transferred to a greenhouse fruiting crop at dawn`**
Blocks — **at every level including `association`** — any claim scoped to *(guard-cell/apoplastic hexose) × (tomato/cucumber/pepper/rose) × (dawn/dark phase)*. Additive to the causal auditor's CANDIDATE ceiling: the crop-and-dawn-scoped association has **zero in-scope supporting evidence and one in-scope crop-scale dissociation**. Specifically blocked: labelling it a crop-applicable mechanism at any confidence; any night-temperature setpoint recommendation **justified by hexose**; any use of dawn leaf sugar as a mechanistic control input or sensor.

**`VETO (secondary): whole-leaf hexose as the exposure construct`** — blocks admission of any whole-leaf/whole-tissue sugar assay as confirming or disconfirming evidence above hypothesis-generating status, **for either sign**.

**NOT vetoed:** the temperature-worded, crop-scoped association ("on clear days in this house, morning gs is lower after cooler nights") at the association level; and **C2 alone** (cool night reduces sink activity in greenhouse tomato), which transfers cleanly and quantitatively.

**Evidence that would lift the veto (all four required, none satisfied today):**
1. **Compartment resolution in the target crop and cultivar** — pre-dawn apoplastic washing fluid with a cytosolic-contamination marker, a guard-cell-enriched fraction separated from mesophyll, guard-cell starch imaging. *A whole-leaf NSC number will not lift this veto at any sample size, because the exposure construct is a different variable, not a noisier one.*
2. **A signed dose-response for that crop's guard cells at measured pre-dawn concentrations**, across the dark→light transition, with equi-osmotic mannitol and a non-metabolisable hexose analogue (3-O-methylglucose). The corpus's closure evidence sits **20–250× above** the physiological apoplastic range and is mannitol-reproducible.
3. **Demonstration that the route operates in the dark/dawn phase** — direct refutation of the dark-inert apoplastic-fluid result in the target crop.
4. **Restoration of the mediator at crop scale** — a target-crop replication in which reduced sink activity raises pre-dawn **hexose specifically** and that rise tracks the gs depression. A2-020's null currently stands unrebutted in the target crop family.

## Declared abstentions
No ResultEnvelope emitted (task forbade writes) → unsealed, not citable by a sealed artifact until the parent persists it; no method-quality assessment (deferred to `method_auditor`); relied on `GATE-GROUNDING-48eabc1bf0842f8e` rather than re-verifying spans; did not read defender/prosecutor/inductivist outputs — **if any of them binds a crop-scale hexose→gs measurement, the SPECIES_GAP count of zero must be re-derived before the veto is adjudicated**. Judgment calls flagged: treating the dark-inert result as decisive for the dawn setting is itself a cross-species inference (strongest available, not proof).
