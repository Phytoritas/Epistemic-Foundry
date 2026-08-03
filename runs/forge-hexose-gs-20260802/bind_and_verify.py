#!/usr/bin/env python3
"""Grounding gate: re-read every claimed span from disk and refuse what drifts.

EF4-I02 (claim-first evidence) demands that a promoted claim resolve to
immutable span evidence. Here that is enforced literally: each claim's
`char_start`/`char_end` is re-extracted from the corpus document and compared
byte-for-byte against the reported `verbatim_text`, and the quote hash is
recomputed. A claim whose span does not re-extract is REFUSED, not softened.

Honest contract deviation recorded by this run
----------------------------------------------
The canonical `source_locator` (shared by claim-card and evidence-node) requires
`page` as an integer >= 1. The paper-curation corpus supplies page-less markdown
text extractions, and form-feed page separators are absent or unusable (verified
on a sample). Emitting a canonical claim-card or evidence-node would therefore
require inventing a page number, which the constitution forbids. This module
consequently emits corpus-native grounded-claim records (document + content hash
+ byte-exact character span + quote hash), which are STRICTLY stronger for
verification than page coordinates, and files an explicit SPEC_GAP instead of
fabricating the missing field.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\dev\insight\Epistemic-Foundry") / "src"))

from epistemic_foundry.contracts import validate_artifact  # noqa: E402
from epistemic_foundry.domain.hashing import hash_excluding  # noqa: E402

CORPUS = Path(r"C:\dev\insight\paper-curation\docs\papers")
RUN_DIR = Path(__file__).resolve().parent
RUN_ID = "FORGE-HEXOSE-GS-20260802"
AT = "2026-08-02T12:00:00.000Z"
POLICY_HASH = "sha256:" + hashlib.sha256(b"FORGE-HEXOSE-GS-20260802/grounding-policy/v1").hexdigest()


def sha256_str(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_doc(document_id: str) -> str | None:
    path = CORPUS / document_id / "text.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    snapshot = json.loads((RUN_DIR / "corpus-snapshot.json").read_text(encoding="utf-8"))
    doc_hash = {u["document_id"]: u["sha256"] for u in snapshot["units"]}

    claim_files = sorted(RUN_DIR.glob("claims_*.json"))
    if not claim_files:
        raise SystemExit("no claims_*.json found; run the extraction roles first")

    verified: list[dict] = []
    refused: list[dict] = []
    cache: dict[str, str | None] = {}

    for cf in claim_files:
        payload = json.loads(cf.read_text(encoding="utf-8"))
        role = payload.get("role", cf.stem)
        for claim in payload.get("claims", []):
            ref = claim.get("claim_ref") or "?"
            doc_id = str(claim.get("document_id") or "")
            if doc_id not in cache:
                cache[doc_id] = load_doc(doc_id)
            text = cache[doc_id]
            if text is None:
                refused.append({"claim_ref": ref, "role": role, "document_id": doc_id,
                                "reason": "document_not_found"})
                continue
            try:
                start = int(claim["char_start"])
                end = int(claim["char_end"])
            except (KeyError, TypeError, ValueError):
                refused.append({"claim_ref": ref, "role": role, "document_id": doc_id,
                                "reason": "span_offsets_missing_or_invalid"})
                continue
            if not (0 <= start < end <= len(text)):
                refused.append({"claim_ref": ref, "role": role, "document_id": doc_id,
                                "reason": f"span_out_of_range(len={len(text)},start={start},end={end})"})
                continue
            actual = text[start:end]
            reported = str(claim.get("verbatim_text") or "")
            if actual != reported:
                refused.append({
                    "claim_ref": ref, "role": role, "document_id": doc_id,
                    "reason": "span_text_mismatch",
                    "actual_prefix": actual[:120],
                    "reported_prefix": reported[:120],
                })
                continue
            recomputed = sha256_str(actual)
            reported_hash = str(claim.get("text_hash") or "")
            if reported_hash and reported_hash != recomputed:
                refused.append({"claim_ref": ref, "role": role, "document_id": doc_id,
                                "reason": "quote_hash_mismatch",
                                "recomputed": recomputed, "reported": reported_hash})
                continue

            span_id = "SPAN-" + hashlib.sha256(
                f"{doc_id}|{start}|{end}".encode("utf-8")
            ).hexdigest()[:24]
            grounded = {
                "grounded_claim_id": "GC-" + hashlib.sha256(
                    f"{doc_id}|{start}|{end}|{claim.get('claim_statement','')}".encode("utf-8")
                ).hexdigest()[:24],
                "run_id": RUN_ID,
                "extractor_role": role,
                "claim_ref": ref,
                "span": {
                    "span_id": span_id,
                    "document_id": doc_id,
                    "document_sha256": doc_hash.get(doc_id),
                    "char_start": start,
                    "char_end": end,
                    "verbatim_text": actual,
                    "quote_sha256": recomputed,
                    "semantic_unit": claim.get("semantic_unit"),
                    "section": claim.get("section"),
                    "page": None,
                    "coordinate_system": "not_available",
                    "parser_name": "paper-curation markdown text extraction (text.md as supplied)",
                    "reconciliation_status": "single_parser",
                    "verification": "byte_exact_reextraction",
                },
                "claim_statement": claim.get("claim_statement"),
                "claim_type": claim.get("claim_type"),
                "author_stance": claim.get("author_stance"),
                "subject": claim.get("subject"),
                "relation": claim.get("relation"),
                "object": claim.get("object"),
                "direction": claim.get("direction"),
                "evidence_layer": claim.get("evidence_layer"),
                "hedging_level": claim.get("hedging_level"),
                "scope": claim.get("scope"),
                "quantitative": claim.get("quantitative"),
                "relevance_to": claim.get("relevance_to"),
                "bearing_on_hypothesis": claim.get("bearing_on_hypothesis"),
                "why": claim.get("why"),
            }
            verified.append(grounded)

    total = len(verified) + len(refused)
    pass_rate = (len(verified) / total) if total else 0.0

    # The gate is a real canonical artifact; only its span primitive is native.
    gate = {
        "gate_id": "GATE-GROUNDING-" + hashlib.sha256(
            f"{RUN_ID}|grounding".encode("utf-8")
        ).hexdigest()[:16],
        "gate_version": "1.0.0",
        "run_id": RUN_ID,
        "name": "claim_span_grounding",
        "status": "PASS" if refused == [] else "FAIL",
        "reasons": (
            [f"all {len(verified)} claim spans re-extracted byte-identically from the corpus"]
            if not refused
            else [f"{len(refused)} of {total} claim spans failed byte-exact re-extraction"]
            + [f"{r['claim_ref']}: {r['reason']}" for r in refused[:20]]
        ),
        "evidence_ids": [g["grounded_claim_id"] for g in verified],
        "input_artifact_ids": [cf.name for cf in claim_files] + [snapshot["snapshot_id"]],
        "policy_bundle_hash": POLICY_HASH,
        "decision": "PASS" if not refused else "FAIL",
        "blocker_ids": [r["claim_ref"] for r in refused],
        "waiver_authority": None,
        "waiver_reason": None,
        "evaluated_at": AT,
        "created_at": AT,
        "policy_version": "1.0.0",
        "non_waivable": True,
        "evaluator_type": "deterministic",
        "input_hash": "sha256:" + hashlib.sha256(
            json.dumps(
                [{"f": cf.name, "sha": hashlib.sha256(cf.read_bytes()).hexdigest()} for cf in claim_files],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "decision_hash": "",
    }
    gate["decision_hash"] = hash_excluding(gate, "decision_hash")
    validate_artifact("gate-decision", gate)

    spec_gap = {
        "spec_gap_id": "SPEC_GAP-SOURCE-LOCATOR-PAGE",
        "run_id": RUN_ID,
        "raised_at": AT,
        "contract": "schemas/claim-card.schema.json and schemas/evidence-node.schema.json, $defs.source_locator",
        "requirement": "source_locator.page is a required integer with minimum 1",
        "corpus_reality": (
            "paper-curation supplies page-less markdown text extractions (text.md); "
            "form-feed page separators were checked on a 60-document sample and are "
            "absent or unusable (3/60 documents, with implausible counts such as 4 "
            "pages for 1.5M characters), so no page number is recoverable"
        ),
        "why_not_resolved_downward": (
            "Emitting a canonical claim-card or evidence-node would require inventing a "
            "page integer. Fabricating a provenance field to satisfy a validator is "
            "exactly what the constitution forbids, so the run refuses and files this gap "
            "instead of producing schema-green but untrue artifacts."
        ),
        "substitute_in_force": (
            "corpus-native grounded-claim records carrying document_id, document sha256, "
            "byte-exact char span, verbatim text and quote sha256, each verified by "
            "re-extraction. For verification purposes this is strictly stronger than a "
            "page coordinate; it is weaker only for human page-level citation."
        ),
        "remediation_options": [
            "re-ingest the corpus from the source PDFs with a page-aware parser and "
            "populate page/bbox for real (the Zotero PDF library is the natural source)",
            "amend the canonical source_locator under manifest authority to represent an "
            "explicitly unavailable page (for example page: null with coordinate_system "
            "'not_available'), so text-only corpora can be first-class",
        ],
        "owner": "primary session (Parent Architect) to route: corpus pipeline (paper-curation) or contract amendment (C-phase schema authority)",
        "blocks": ["canonical claim-card emission", "canonical evidence-node emission"],
        "does_not_block": [
            "byte-exact span grounding",
            "gate-decision artifacts",
            "adjudication",
            "minority-report",
            "argument-graph",
        ],
    }

    out = {
        "run_id": RUN_ID,
        "recorded_at_utc": AT,
        "counts": {
            "claims_submitted": total,
            "claims_verified": len(verified),
            "claims_refused": len(refused),
            "grounding_pass_rate": round(pass_rate, 4),
            "documents_cited": len({g["span"]["document_id"] for g in verified}),
        },
        "by_bearing": {},
        "by_link": {},
        "gate": gate,
        "spec_gap": spec_gap,
        "refused": refused,
    }
    for g in verified:
        b = g.get("bearing_on_hypothesis") or "unspecified"
        out["by_bearing"][b] = out["by_bearing"].get(b, 0) + 1
        for link in (g.get("relevance_to") or ["unspecified"]):
            out["by_link"][link] = out["by_link"].get(link, 0) + 1

    (RUN_DIR / "grounded-claims.json").write_text(
        json.dumps({"run_id": RUN_ID, "claims": verified}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUN_DIR / "grounding-report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: out[k] for k in ("counts", "by_bearing", "by_link")}, ensure_ascii=False, indent=2))
    print("gate:", gate["status"], "| refused:", len(refused))
    if refused:
        for r in refused[:12]:
            print("  REFUSED", r["claim_ref"], r["reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
