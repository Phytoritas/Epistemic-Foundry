"""The cross-language contract generator must be run, and its state declared.

`packages/contracts/codegen/generate.py` is the declared authority for the
TypeScript, JavaScript and Python contract projections shipped under `web/`,
`packages/` and `python/`. A review found that after a canonical schema
amendment those projections still embedded the pre-amendment source digest, that
two of them were sealed-pinned and byte-unchanged so the pin gate passed them,
and — the part that let it persist — that **nothing in the repository ever
invoked the generator**. A source of truth nobody runs is a source of truth
nobody checks.

This gate runs it. Two states are distinguished, because they mean different
things:

* `stale generated file` means a projection no longer matches the schemas it was
  generated from. That is always a failure: it is the dependent-projection
  defect, shipped to consumers.
* `unexpected generated file` means the generator found a file in its output
  directory that it does not own. Three such files exist —
  `web/src/generated/ui-client/*` — written by a different generator. They are
  tracked content, they are imported by `tests/ui/ui-surface.mjs`, and running
  `--write` deletes them. That ownership conflict predates this gate and is not
  resolved here; what is refused is letting it hide a stale projection, and
  letting the generator's exit code be reported as passing when it is not.

The earlier claim that `--check` "now reports 0" was wrong in exactly that way:
zero *stale*, three *unexpected*, real exit code 1.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from epistemic_foundry.contracts import repo_root

GENERATOR = "packages/contracts/codegen/generate.py"

#: Files the generator reports as unexpected because a different generator owns
#: them. Exact set: a fourth would mean either a new owner or a real leak.
KNOWN_FOREIGN_OUTPUT = {
    "web/src/generated/ui-client/index.d.ts",
    "web/src/generated/ui-client/index.mjs",
    "web/src/generated/ui-client/route-manifest.json",
}


def _check() -> dict:
    result = subprocess.run(
        [sys.executable, "-B", GENERATOR, "--check"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:  # pragma: no cover - generator broke
        pytest.fail(f"generator produced no JSON report: {result.stdout[:400]}")


def test_no_generated_projection_is_stale() -> None:
    """The failure that ships a wrong digest to consumers."""
    failures = _check().get("failures") or []
    stale = sorted(item for item in failures if item.startswith("stale generated file"))
    assert not stale, (
        "cross-language contract projections no longer match the schemas they "
        f"were generated from; run `python {GENERATOR} --write`: {stale}"
    )


def test_foreign_output_in_the_generated_tree_is_exactly_the_known_set() -> None:
    """Declare the ownership conflict; refuse to let it grow or hide anything."""
    failures = _check().get("failures") or []
    unexpected = {
        item.split("unexpected generated file: ", 1)[-1]
        for item in failures
        if item.startswith("unexpected generated file")
    }
    assert unexpected == KNOWN_FOREIGN_OUTPUT, (
        "the set of files the contract generator does not recognise changed. "
        f"expected {sorted(KNOWN_FOREIGN_OUTPUT)}, found {sorted(unexpected)}. "
        "Either a new generator started writing here, or files this one owns "
        "went missing — both need a decision, not a silent pass."
    )


def test_the_generators_own_verdict_is_reported_honestly() -> None:
    """The report must not be read as passing while the generator fails.

    This is the assertion that would have caught the false claim: the run does
    fail, for a declared reason, and that is recorded rather than rounded down
    to success.
    """
    report = _check()
    assert report["status"] == "FAIL", (
        "the generator now passes; delete KNOWN_FOREIGN_OUTPUT and this test's "
        "premise rather than leaving a stale exception in place"
    )
    assert not [
        item
        for item in report.get("failures") or []
        if not item.startswith("unexpected generated file")
    ], "the generator fails for a reason other than the declared ownership conflict"
