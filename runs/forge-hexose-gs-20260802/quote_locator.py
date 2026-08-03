#!/usr/bin/env python3
"""Locate an exact quote inside a corpus document and emit verifiable offsets.

Usage:
  python quote_locator.py <document_id> "<search phrase>"          # find offsets
  python quote_locator.py <document_id> --slice <start> <end>      # read a slice
  python quote_locator.py <document_id> --grep "<regex>" [n]       # list matches

Offsets are indices into `Path(text.md).read_text(encoding="utf-8",
errors="replace")`, which is exactly how the grounding verifier re-reads them.
Use the emitted char_start/char_end and verbatim_text verbatim; a claim whose
span does not re-extract byte-identically is refused downstream.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

CORPUS = Path(r"C:\dev\insight\paper-curation\docs\papers")


def load(document_id: str) -> str:
    path = CORPUS / document_id / "text.md"
    if not path.is_file():
        matches = sorted(p for p in CORPUS.glob(f"{document_id}*") if (p / "text.md").is_file())
        if not matches:
            raise SystemExit(f"no such document: {document_id}")
        path = matches[0] / "text.md"
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    document_id = sys.argv[1]
    text = load(document_id)

    if sys.argv[2] == "--slice":
        start, end = int(sys.argv[3]), int(sys.argv[4])
        quote = text[start:end]
        print(json.dumps({
            "document_id": document_id,
            "char_start": start,
            "char_end": end,
            "verbatim_text": quote,
            "text_hash": "sha256:" + hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        }, ensure_ascii=False, indent=2))
        return 0

    if sys.argv[2] == "--grep":
        pattern = sys.argv[3]
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 8
        out = []
        for m in re.finditer(pattern, text, re.IGNORECASE):
            s = max(0, m.start() - 200)
            e = min(len(text), m.end() + 200)
            out.append({"match_at": m.start(), "context_start": s, "context_end": e,
                        "context": text[s:e].replace("\n", " ")})
            if len(out) >= limit:
                break
        print(json.dumps({"document_id": document_id, "matches": out}, ensure_ascii=False, indent=2))
        return 0

    phrase = sys.argv[2]
    idx = text.find(phrase)
    if idx < 0:
        # tolerate whitespace/newline differences
        loose = re.compile(re.escape(phrase).replace(r"\ ", r"\s+"), re.IGNORECASE)
        m = loose.search(text)
        if not m:
            print(json.dumps({"found": False, "document_id": document_id}, ensure_ascii=False))
            return 1
        start, end = m.start(), m.end()
    else:
        start, end = idx, idx + len(phrase)
    quote = text[start:end]
    print(json.dumps({
        "found": True,
        "document_id": document_id,
        "char_start": start,
        "char_end": end,
        "verbatim_text": quote,
        "text_hash": "sha256:" + hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
