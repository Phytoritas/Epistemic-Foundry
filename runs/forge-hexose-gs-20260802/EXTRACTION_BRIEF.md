# Claim-extraction brief — FORGE-HEXOSE-GS-20260802

You are a bounded role in an Epistemic Foundry v4 FORGE run. You read REAL paper
text and emit atomic, source-anchored claims. You do NOT judge the hypothesis;
downstream roles (parliament, auditors, judge) do that. Overclaiming, guessing a
quote, or reporting a span that does not re-extract byte-identically is a
FAILURE — every span you emit is re-read from disk and compared.

## Corpus
Root: `C:\dev\insight\paper-curation\docs\papers\<document_id>\text.md`
(1,281 papers, full extracted text; snapshot `CSNAP-8e1c4c767aef2c7cac93976da0fd44aa`).

## Hypothesis under test (do NOT try to confirm it — characterize the evidence)
> Stomatal conductance is modulated by hexose. On otherwise-equivalent clear
> days, morning stomatal opening is reduced when the preceding day had adequate
> light but temperature too low for growth, because reduced overnight conversion
> of hexose into structural carbohydrate leaves residual hexose that suppresses
> stomatal opening.

Decomposed links:
- **C1** Hexose (glucose/fructose) modulates stomatal aperture/conductance.
- **C2** Low night temperature limits growth / structural-carbohydrate conversion (sink activity).
- **C3** Reduced overnight structural conversion leaves elevated residual leaf hexose at dawn.
- **C4** Elevated dawn leaf hexose causally reduces morning stomatal opening on a clear day.

## Tooling for verifiable spans (use it — do not hand-count offsets)
```
cd C:\dev\insight\Epistemic-Foundry
uv run --locked python -B runs/forge-hexose-gs-20260802/quote_locator.py <document_id> "<exact phrase>"
uv run --locked python -B runs/forge-hexose-gs-20260802/quote_locator.py <document_id> --grep "<regex>" 10
uv run --locked python -B runs/forge-hexose-gs-20260802/quote_locator.py <document_id> --slice <start> <end>
```
`--grep` gives context windows; then quote a sentence from that context and run
the plain form to get `char_start` / `char_end` / `verbatim_text` / `text_hash`.
Copy those fields into your output unchanged.

## What counts as a good claim
- **Atomic**: one subject–relation–object, not a paragraph summary.
- **Directional**: say whether the effect is positive / negative / null / nonmonotonic / mixed.
- **Scoped**: species, tissue or compartment (apoplast vs symplast vs guard cell),
  conditions (light, temperature, CO2), timescale (seconds-minutes vs hours vs days).
  Compartment and timescale are load-bearing here — record them whenever stated.
- **Layered**: `direct_measurement`, `primary_analysis`, `modeling`, `formal_derivation`,
  `benchmark_execution`, `review`, `background`, `unsupported`.
- **Honest about stance**: `asserted`, `supported`, `suggested`, `speculative`,
  `qualified`, `negated`, `unclear`. A review restating someone else is `review`, not measurement.
- **Contradicting evidence is as valuable as supporting evidence.** If a paper says
  sugars PROMOTE stomatal opening, that is a first-class finding, not a problem.

## Output — write ONE file: `<your assigned output path>`
JSON: `{"role": "...", "documents_read": [...], "claims": [ ... ], "notes": "..."}`

Each claim object:
```json
{
  "claim_ref": "A1-001",
  "document_id": "1106_Mesophyllderived_sugars_are_positive_regulators_of_lightdriv",
  "semantic_unit": "abstract|introduction|methods|results|discussion|conclusion|figure_caption|table_caption|other",
  "section": "free-text section label or null",
  "char_start": 1234, "char_end": 1456,
  "verbatim_text": "<exact text, copied from the locator output>",
  "text_hash": "sha256:...",
  "claim_statement": "atomic restatement in one sentence",
  "claim_type": "observation|association|causal|mechanism|theory|model|method|limitation|review_synthesis|background_assertion|speculation",
  "author_stance": "asserted|supported|suggested|speculative|qualified|negated|unclear",
  "subject": "...", "relation": "...", "object": "...",
  "direction": "positive|negative|null|nonmonotonic|mixed|not_applicable|unknown",
  "evidence_layer": "direct_measurement|primary_analysis|modeling|formal_derivation|benchmark_execution|review|background|unsupported",
  "hedging_level": 0,
  "scope": {"species": "...", "compartment": "...", "conditions": "...", "timescale": "..."},
  "quantitative": {"magnitude_text": "... or null", "effect_size": null, "sample_size": null, "p_value": null},
  "relevance_to": ["C1"],
  "bearing_on_hypothesis": "supports|contradicts|conditions|neutral",
  "why": "one sentence on why it bears that way"
}
```

## Hard rules
- Never invent a quote, offset, hash, number, species, or citation. If you cannot
  verify a span with the locator, drop the claim and say so in `notes`.
- Do not modify anything outside your single output file.
- Prefer 15–35 high-quality claims over a long shallow list; concentrate on the
  load-bearing links, and always include the strongest contradicting material you find.
- If a link (C1..C4) has no evidence in your assigned papers, say so explicitly in
  `notes` — absence in your set is absence of evidence in your set, never proof of absence.
