#!/usr/bin/env python3
"""Recover F04-0002 after its core generation committed before binding."""

from __future__ import annotations

import json
import sys


sys.dont_write_bytecode = True

import f04_0002_rah_seal as seal


EXPECTED_ATTEMPT_ID = "F04-0002"
EXPECTED_CORE_GENERATION = "000006-94d31a33"
EXPECTED_CORE_EVIDENCE_ID = "E0006"
EXPECTED_FINAL_EVIDENCE_ID = "E0007"


def main() -> int:
    # The original sealer committed E0006 before failing because this constant
    # was accidentally omitted. Inject it without changing the hash-sealed file.
    seal.ATTEMPT_ID = EXPECTED_ATTEMPT_ID

    _, generation, payloads = seal.current_state()
    identifiers = seal.evidence_ids(payloads)
    ledger_entries = payloads["evidence_ledger.json"]["entries"]
    if generation != EXPECTED_CORE_GENERATION:
        raise SystemExit(
            f"refusing recovery from generation {generation}; "
            f"expected {EXPECTED_CORE_GENERATION}"
        )
    if identifiers[-1:] != [EXPECTED_CORE_EVIDENCE_ID]:
        raise SystemExit(
            f"refusing recovery from ledger tail {identifiers[-1:]}; "
            f"expected {EXPECTED_CORE_EVIDENCE_ID}"
        )
    if ledger_entries[-1].get("summary") != seal.core_summary():
        raise SystemExit("E0006 summary differs from the hash-sealed F04 core summary")

    integrity = seal.verify_generation_store(6)
    seal.write_json(seal.ATTEMPT / "rah-core-integrity.json", integrity)
    seal.evidence.bind_rah_state(
        core_generation=EXPECTED_CORE_GENERATION,
        core_evidence_id=EXPECTED_CORE_EVIDENCE_ID,
        final_closeout_evidence_id=EXPECTED_FINAL_EVIDENCE_ID,
    )
    seal.evidence.verify()

    final_result = seal.run_final()
    verification = seal.run_verify()
    print(
        json.dumps(
            {
                "mode": "recover-after-core",
                "status": "PASS",
                "core_generation": EXPECTED_CORE_GENERATION,
                "core_evidence_id": EXPECTED_CORE_EVIDENCE_ID,
                "final": final_result,
                "verification": verification,
                "completion_ready": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
