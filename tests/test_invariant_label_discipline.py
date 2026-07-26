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


def test_no_invariant_is_cited_from_two_unrelated_test_modules() -> None:
    """A label appearing in several test files usually means a copied section
    header drifted. Enforcement may legitimately span source modules, so only
    test-file citations are constrained here."""
    per_label: dict[str, set[str]] = {}
    for label, locations in cited_labels().items():
        files = {
            location.split(":", 1)[0]
            for location in locations
            if location.startswith("tests/")
        }
        if files:
            per_label[label] = files
    offenders = {label: sorted(files) for label, files in per_label.items() if len(files) > 1}
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
def test_previously_drifted_labels_keep_their_spec_title(label: str, expected_title: str) -> None:
    """These twelve numbers were once cited one position off (or swapped), which
    made recorded coverage evidence point at a neighbouring invariant. Pinning the
    titles turns a repeat of that mistake into a test failure."""
    assert spec_invariants()[label] == expected_title
