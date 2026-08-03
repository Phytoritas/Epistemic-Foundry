"""Every EF4-I citation in code or tests must name the invariant it enforces.

Invariant labels are the only link between a module and the constitutional clause
it implements. A drifted number is worse than no citation: the coverage evidence
then claims a different invariant is enforced than the one the code actually
enforces, and a reviewer reading the docstring is pointed at the wrong contract.

`MASTER_SPEC.md` is the authority for the numbering and
`manifests/product_invariants.yaml` must agree with it, so this test checks both
the numbering itself and that every citation resolves to a declared invariant.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "MASTER_SPEC.md"
MANIFEST_PATH = REPO_ROOT / "manifests" / "product_invariants.yaml"

HEADING = re.compile(r"^### (EF4-I\d{2}) — (.+)$")
CITATION = re.compile(r"EF4-I\d{2}")

#: How many invariants the constitution declares. Named here so a silent
#: truncation of the spec is a failure rather than a smaller passing check.
EXPECTED_INVARIANT_COUNT = 64


def spec_invariants() -> dict[str, str]:
    titles: dict[str, str] = {}
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line.strip())
        if match:
            titles[match.group(1)] = match.group(2).strip()
    return titles


def cited_labels() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "src").rglob("*.py")) + sorted(
        (REPO_ROOT / "tests").rglob("*.py")
    ):
        if path.name == Path(__file__).name:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label in CITATION.findall(line):
                found.setdefault(label, []).append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}"
                )
    return found


def test_spec_declares_a_contiguous_invariant_numbering() -> None:
    titles = spec_invariants()
    assert len(titles) == EXPECTED_INVARIANT_COUNT
    expected = [f"EF4-I{index:02d}" for index in range(1, EXPECTED_INVARIANT_COUNT + 1)]
    assert sorted(titles) == expected


def test_manifest_ids_match_the_spec_headings() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_ids = [str(entry["id"]) for entry in manifest["invariants"]]
    assert manifest_ids == sorted(spec_invariants())


def test_every_cited_label_exists_in_the_spec() -> None:
    titles = spec_invariants()
    unknown = {
        label: locations
        for label, locations in cited_labels().items()
        if label not in titles
    }
    assert unknown == {}


#: Invariants whose enforcement genuinely spans more than one test module, with
#: the reason. The rule below is a drift heuristic — it assumes a repeated label
#: means a copied header — and a review found the case it does not model: an
#: invariant with two distinct enforcement surfaces. Suppressing the true
#: citation to satisfy the heuristic made `rg EF4-I38 tests/` under-report which
#: tests enforce it, which is the same wrong-coverage-evidence the rule exists to
#: prevent. An entry here must name every file and say why they are not drift.
MULTI_MODULE_INVARIANTS: dict[str, dict[str, object]] = {
    "EF4-I38": {
        "files": {
            "tests/test_updates.py",
            "tests/packaging/test_receipt_invalidation.py",
        },
        "reason": (
            "Downstream invalidation has two enforcement surfaces that do not "
            "overlap: test_updates.py covers the runtime update path, where new "
            "evidence invalidates a claim, and test_receipt_invalidation.py "
            "covers the build and evidence-graph path, where a canonical "
            "correction invalidates the receipts projecting it. Neither is a "
            "copy of the other and neither subsumes the other."
        ),
    },
}


def test_multi_module_allowlist_is_exact_and_justified() -> None:
    """An allowlist that outlives its reason becomes a blanket exemption."""
    for label, entry in MULTI_MODULE_INVARIANTS.items():
        assert str(entry["reason"]).strip(), f"{label} allowlisted with no reason"
        cited = {
            location.split(":", 1)[0]
            for location in cited_labels().get(label, [])
            if location.startswith("tests/")
        }
        assert cited == entry["files"], (
            f"{label} is allowlisted for {sorted(entry['files'])} but is cited "
            f"from {sorted(cited)}; update the allowlist deliberately rather "
            "than letting it drift into cover for a real duplicate"
        )


def test_no_invariant_is_cited_from_two_unrelated_test_modules() -> None:
    """A label appearing in several test files usually means a copied section
    header drifted. Enforcement may legitimately span source modules, so only
    test-file citations are constrained here. The exceptions are enumerated in
    MULTI_MODULE_INVARIANTS, which requires the exact file set and a reason."""
    per_label: dict[str, set[str]] = {}
    for label, locations in cited_labels().items():
        files = {
            location.split(":", 1)[0]
            for location in locations
            if location.startswith("tests/")
        }
        if files:
            per_label[label] = files
    offenders = {
        label: sorted(files)
        for label, files in per_label.items()
        if len(files) > 1
        and files != MULTI_MODULE_INVARIANTS.get(label, {}).get("files")
    }
    assert offenders == {}


@pytest.mark.parametrize(
    ("label", "expected_title"),
    [
        ("EF4-I11", "Evidence-class separation"),
        ("EF4-I12", "No self-approval"),
        ("EF4-I51", "Typed crossover"),
        ("EF4-I52", "Red Queen relevance"),
        ("EF4-I54", "Delayed reward routing"),
        ("EF4-I55", "Prompt evolution quarantine"),
        ("EF4-I56", "Evaluator updates are future-only"),
        ("EF4-I57", "Surrogate is triage only"),
        ("EF4-I58", "Replication-gated promotion"),
        ("EF4-I60", "Exact candidate reconciliation"),
        ("EF4-I61", "Atomic evolution checkpoints"),
        ("EF4-I62", "Typed stop certificate"),
    ],
)
def test_previously_drifted_labels_keep_their_spec_title(
    label: str, expected_title: str
) -> None:
    """These twelve numbers were once cited one position off (or swapped), which
    made recorded coverage evidence point at a neighbouring invariant. Pinning the
    titles turns a repeat of that mistake into a test failure."""
    assert spec_invariants()[label] == expected_title
