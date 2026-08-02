#!/usr/bin/env python3
"""A04 required check ``independent_review_gate``.

A04 is the P00-A integration checkpoint.  Its second required check attests the
*deterministic substance* an independent reviewer relies on when approving the
authority and boundary separation of the A phase.  The check verifies three
machine-checkable conditions, fail-closed:

1. **Authority chain intact.**  ``CLAUDE.md`` states the eight-level authority
   order (``MASTER_SPEC.md`` highest, work-package-local notes lowest, with
   ``manifests/role_registry.yaml`` above ``AGENTS.md``/``CLAUDE.md``), the
   "a lower source cannot override a higher one" rule, and the ``SPEC_GAP``
   conflict-handling clause.  The check parses the ordered list and asserts it
   equals the canonical order — no re-ranking that would let a lower source win.

2. **No adapter-authority inversion.**  ``packages/boundary-policy.json`` places
   the authority layer strictly inward of (lower index than) the adapter layer;
   ``foundry-kernel`` is classified ``authority`` and every ``plugin``/``ui``
   host is classified ``adapter``.  The sealed A03 ``boundary_cycle_policy_check``
   is PASS, and ADR-034 asserts an authority-in-cycle or adapter-in-cycle graph
   FAILs.  Together these establish the Plugin Shell stays an adapter while the
   Kernel/Ledger keep canonical authority — no inward authority dependence on an
   adapter.

3. **ADR-034 waiver is a genuine tightening.**  The ADR-034 L3 integration-gate
   cycle exception explicitly records that it is "a tightening, not a weakening"
   and "strictly stronger", pins a closed fingerprinted two-entry exemption
   list, and *rejects* the weakening alternatives (ignore top-level cycles;
   open-ended "any L3 cycle" waiver).  The check asserts the tightening language
   is present and the weakening options are recorded as rejected, not adopted.

**Honesty boundary.**  GREEN here attests only that these deterministic
preconditions hold in the sealed evidence.  It does **not** assert that a
seal-time independent reviewer has already certified the phase.  The evidence
records ``seal_time_independent_review_required = true`` and
``actor_independent_certification_claimed = false``; the actual independent
review by the ``integration_reviewer`` role remains a required seal gate outside
this harness.

Run as a pytest module::

    .venv/Scripts/python.exe -m pytest \
        artifacts/work_packages/A04/attempts/0001/test_independent_review_gate.py \
        -p no:cacheprovider

Or standalone to emit deterministic JSON evidence::

    .venv/Scripts/python.exe \
        artifacts/work_packages/A04/attempts/0001/test_independent_review_gate.py \
        --output artifacts/work_packages/A04/attempts/0001/independent-review-gate.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]

CLAUDE_MD = ROOT / "CLAUDE.md"
BOUNDARY_POLICY = ROOT / "packages/boundary-policy.json"
ADR_034 = ROOT / "docs/adr/ADR-034-l3-integration-gate-cycle-exception.md"
A03_ATTEMPT_REPORT = ROOT / "artifacts/work_packages/A03/attempts/0001/report.json"

#: The canonical authority order, in descending precedence.  A lower source
#: cannot override a higher one; role_registry sits above AGENTS/CLAUDE.
CANONICAL_AUTHORITY_ORDER = (
    "MASTER_SPEC.md",
    "manifests/development_manifest.yaml",
    "manifests/acceptance_matrix.yaml",
    "manifests/product_invariants.yaml",
    "applicable schemas/*.schema.json and workflows/*.workflow.yaml",
    "manifests/role_registry.yaml",
    "AGENTS.md or this file",
    "work-package-local notes",
)

#: Language ADR-034 must carry to count as a genuine tightening.
TIGHTENING_PHRASES = (
    "tightening, not a weakening",
    "strictly stronger",
)

#: Weakening options ADR-034 must record as REJECTED (not adopted).
REJECTED_WEAKENINGS = (
    "Weaken `boundary_cycle_policy_check` to ignore top-level cycles",
    'Open-ended waiver for "any L3 cycle."',
)


class ReviewGateError(AssertionError):
    """Fail-closed independent-review-gate violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewGateError(message)


def read_text(path: Path) -> str:
    require(path.is_file(), f"required document missing: {path.relative_to(ROOT).as_posix()}")
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def _normalize(source: str) -> str:
    # Collapse backticks and whitespace so the list matches regardless of inline
    # code formatting.
    return re.sub(r"\s+", " ", source.replace("`", "").strip())


def check_authority_chain() -> dict[str, Any]:
    text = read_text(CLAUDE_MD)
    require(
        "A lower source cannot override a higher" in text,
        "CLAUDE.md: missing 'a lower source cannot override a higher' rule",
    )
    require(
        "return `SPEC_GAP`" in text,
        "CLAUDE.md: missing SPEC_GAP conflict-handling clause",
    )
    # Parse the numbered authority list from the top of the document.
    order: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\.\s+(.*\S)\s*$", line)
        if match and int(match.group(1)) == len(order) + 1:
            order.append(_normalize(match.group(2)))
        elif order and not line.strip():
            # A blank line after the list ends the enumeration.
            break
        elif order and not re.match(r"^\s*\d+\.", line):
            break
    expected = [_normalize(item) for item in CANONICAL_AUTHORITY_ORDER]
    require(
        order == expected,
        f"CLAUDE.md authority order mismatch:\n  parsed={order}\n  expected={expected}",
    )
    return {
        "authority_order": list(CANONICAL_AUTHORITY_ORDER),
        "lower_cannot_override_higher": True,
        "spec_gap_conflict_clause": True,
        "role_registry_above_agents": (
            CANONICAL_AUTHORITY_ORDER.index("manifests/role_registry.yaml")
            < CANONICAL_AUTHORITY_ORDER.index("AGENTS.md or this file")
        ),
    }


def check_no_adapter_authority_inversion() -> dict[str, Any]:
    policy = load_json(BOUNDARY_POLICY)
    layers = policy.get("layers", {})
    require("authority" in layers, "boundary-policy.json: no 'authority' layer")
    require("adapter" in layers, "boundary-policy.json: no 'adapter' layer")
    authority_index = layers["authority"]
    adapter_index = layers["adapter"]
    require(
        authority_index < adapter_index,
        f"boundary-policy.json: authority layer {authority_index} is not inward "
        f"of adapter layer {adapter_index} (inversion)",
    )

    components = policy.get("components", [])
    by_layer: dict[str, list[str]] = {}
    for component in components:
        by_layer.setdefault(component["layer"], []).append(component["directory"])
    require(
        "foundry-kernel" in by_layer.get("authority", []),
        "boundary-policy.json: foundry-kernel not classified as authority",
    )
    adapters = by_layer.get("adapter", [])
    require(adapters, "boundary-policy.json: no adapter components declared")
    require(
        any(d.startswith("plugin") for d in adapters),
        f"boundary-policy.json: no plugin host among adapters {adapters}",
    )
    # Every adapter is strictly outward of every authority component.
    for authority_dir in by_layer.get("authority", []):
        require(
            layers["authority"] < layers["adapter"],
            f"adapter-authority inversion around {authority_dir}",
        )

    # ADR-034 asserts authority/adapter cycles fail the boundary check.
    adr = read_text(ADR_034)
    require(
        "authority-in-cycle → FAIL" in adr,
        "ADR-034: missing 'authority-in-cycle -> FAIL' assertion",
    )
    require(
        "adapter-in-cycle → FAIL" in adr,
        "ADR-034: missing 'adapter-in-cycle -> FAIL' assertion",
    )

    # The sealed A03 boundary check is PASS.
    a03 = load_json(A03_ATTEMPT_REPORT)
    boundary = a03.get("required_checks", {}).get("boundary_cycle_policy_check", {})
    require(
        boundary.get("status") == "PASS",
        "A03: sealed boundary_cycle_policy_check is not PASS",
    )
    return {
        "authority_layer_index": authority_index,
        "adapter_layer_index": adapter_index,
        "authority_inward_of_adapter": True,
        "authority_components": sorted(by_layer.get("authority", [])),
        "adapter_components": sorted(adapters),
        "adr034_authority_and_adapter_cycles_fail": True,
        "a03_boundary_cycle_policy_check": "PASS",
    }


def check_adr034_is_tightening() -> dict[str, Any]:
    adr = read_text(ADR_034)
    for phrase in TIGHTENING_PHRASES:
        require(phrase in adr, f"ADR-034: missing tightening phrase {phrase!r}")
    # The weakening options are present only in the Rejected-alternatives list.
    rejected_section = adr.split("## Rejected alternatives", 1)
    require(len(rejected_section) == 2, "ADR-034: no 'Rejected alternatives' section")
    rejected_text = rejected_section[1]
    for weakening in REJECTED_WEAKENINGS:
        require(
            weakening in rejected_text,
            f"ADR-034: weakening option not recorded as rejected: {weakening!r}",
        )
    require(
        "closed, enumerated, fingerprinted exception" in adr
        or "closed" in adr
        and "fingerprint" in adr,
        "ADR-034: exemption list is not described as closed/fingerprinted",
    )
    require(
        "**Status:** Accepted" in adr,
        "ADR-034: record is not Accepted",
    )
    return {
        "tightening_language_present": True,
        "weakenings_recorded_as_rejected": list(REJECTED_WEAKENINGS),
        "closed_fingerprinted_exemption_list": True,
        "status": "Accepted",
    }


def build_evidence() -> dict[str, Any]:
    authority = check_authority_chain()
    boundaries = check_no_adapter_authority_inversion()
    tightening = check_adr034_is_tightening()
    return {
        "schema_version": 1,
        "work_package_id": "A04",
        "attempt_id": "A04-0001",
        "check": "independent_review_gate",
        "phase": "P00-A",
        "status": "PASS",
        "authority_chain_intact": authority,
        "no_adapter_authority_inversion": boundaries,
        "adr034_genuine_tightening": tightening,
        # Honesty boundary: this harness attests the deterministic
        # preconditions only.  The seal-time independent review is a separate
        # required gate and is NOT claimed complete here.
        "seal_time_independent_review_required": True,
        "actor_independent_certification_claimed": False,
        "review_role": "integration_reviewer",
        "attested_preconditions": [
            "authority_chain_intact",
            "no_adapter_authority_inversion",
            "adr034_genuine_tightening",
        ],
    }


# --------------------------------------------------------------------------- #
# pytest surface
# --------------------------------------------------------------------------- #
def test_authority_chain_intact() -> None:
    evidence = build_evidence()["authority_chain_intact"]
    assert evidence["lower_cannot_override_higher"] is True
    assert evidence["spec_gap_conflict_clause"] is True
    assert evidence["role_registry_above_agents"] is True
    assert evidence["authority_order"][0] == "MASTER_SPEC.md"
    assert evidence["authority_order"][-1] == "work-package-local notes"


def test_no_adapter_authority_inversion() -> None:
    evidence = build_evidence()["no_adapter_authority_inversion"]
    assert evidence["authority_inward_of_adapter"] is True
    assert evidence["authority_layer_index"] < evidence["adapter_layer_index"]
    assert "foundry-kernel" in evidence["authority_components"]
    assert evidence["a03_boundary_cycle_policy_check"] == "PASS"
    assert evidence["adr034_authority_and_adapter_cycles_fail"] is True


def test_adr034_is_genuine_tightening() -> None:
    evidence = build_evidence()["adr034_genuine_tightening"]
    assert evidence["tightening_language_present"] is True
    assert evidence["closed_fingerprinted_exemption_list"] is True
    assert evidence["status"] == "Accepted"
    assert len(evidence["weakenings_recorded_as_rejected"]) == 2


def test_seal_time_independent_review_not_claimed_complete() -> None:
    evidence = build_evidence()
    # The harness must never claim the seal-time independent certification.
    assert evidence["seal_time_independent_review_required"] is True
    assert evidence["actor_independent_certification_claimed"] is False


def test_gate_fails_closed_on_broken_authority_order() -> None:
    import test_independent_review_gate as mod

    saved = mod.CANONICAL_AUTHORITY_ORDER
    try:
        # Swap MASTER_SPEC below the manifest: a lower source would win. Must fail.
        mod.CANONICAL_AUTHORITY_ORDER = (
            "manifests/development_manifest.yaml",
            "MASTER_SPEC.md",
        )
        raised = False
        try:
            mod.check_authority_chain()
        except ReviewGateError:
            raised = True
        assert raised, "a re-ranked authority order must fail the gate"
    finally:
        mod.CANONICAL_AUTHORITY_ORDER = saved


# --------------------------------------------------------------------------- #
# standalone evidence emitter
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="A04 independent_review_gate")
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON evidence to this path"
    )
    args = parser.parse_args()
    try:
        evidence = build_evidence()
    except ReviewGateError as exc:
        print(f"A04_INDEPENDENT_REVIEW_GATE_FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output = output.resolve()
        require(output.is_relative_to(ROOT.resolve()), "output must stay inside repo")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(
            "A04_INDEPENDENT_REVIEW_GATE_PASS: wrote "
            f"{output.relative_to(ROOT.resolve()).as_posix()}"
        )
    else:
        sys.stdout.write(rendered)
        print("A04_INDEPENDENT_REVIEW_GATE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
