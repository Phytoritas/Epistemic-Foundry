"""A correction must invalidate the projections that depend on it.

`manifests/product_invariants.yaml` (EF4-I38) says corrections, retractions,
parser fixes, policy changes and new evidence invalidate dependent projections.
The pin-supersession gate checks *files*; it compares bytes, so a sealed receipt
whose bytes never changed sails through it while still asserting a verified
projection of a tree that no longer exists. A review named this the sharpest
form of the problem: the change was clean at the file layer while the evidence
graph went on asserting the superseded value.

Sealed receipts are immutable and are not edited here. Their assertions were
true when written and stay in the record. What this gate requires is that the
*dependency* is declared: every artifact that still asserts a superseded
canonical value must appear in `artifacts/work_packages/receipt-invalidations.json`
under the `INVALIDATED` status the taxonomy already defines for exactly this
case — previously accepted output voided because a dependency changed.

An earlier version of this docstring claimed the registry "is derived from the
superseded values, not hand-listed, so it cannot quietly fall behind". That was
false as written and a review demonstrated the consequence: only the
receipts-per-value mapping was derived, while the *value list itself* was
hand-maintained, so deleting one value from it made every dependent asserting
that value invisible and the suite still passed. The value list is now derived
too — `_derived_superseded_values` recomputes the live canonical values and
finds every recorded value that disagrees with them — and the declaration is
checked against that derivation rather than trusted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from epistemic_foundry.contracts import repo_root
from epistemic_foundry.domain.status import CapabilityStatus

REGISTRY_PATH = Path("artifacts/work_packages/receipt-invalidations.json")
SUPERSESSION_PATH = Path("artifacts/work_packages/pin-supersessions.json")

#: Registries that describe the invalidation rather than participating in it.
EXCLUDED_NAMES = {
    "pin-supersessions.json",
    "pin-census.json",
    "receipt-invalidations.json",
}


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _registry() -> dict:
    path = repo_root() / REGISTRY_PATH
    assert path.is_file(), f"{REGISTRY_PATH} is missing; the gate cannot run open"
    return json.loads(path.read_text(encoding="utf-8"))


def _superseded_values() -> set[str]:
    """Canonical values this registry declares retired.

    Read from the registry's own declaration rather than from the pin
    supersessions, because the two sets are not the same: a bundle hash can be
    retired without any individual file pin naming it, and that is exactly the
    dependent-projection case this gate exists for. Whether the declaration is
    *true* is checked separately against the live projection.
    """
    return {str(entry["value"]) for entry in _registry()["superseded_values"]}


#: Keys under which a receipt records a canonical value that can go stale.
CANONICAL_VALUE_KEYS = (
    "source_bundle_hash",
    "projected_snapshot_bundle_hash",
    "build_source_revision",
    "source_revision",
    "registry_hash",
)


def _live_canonical_values() -> set[str]:
    """What the tree produces right now, recomputed rather than read."""
    from scripts.build.canonical_registry.materialize import build_registry_document

    manifest, _ = build_registry_document(repo_root())
    return {
        str(manifest["source_bundle_hash"]),
        str(manifest["projected_snapshot_bundle_hash"]),
        _digest(
            repo_root() / "src/epistemic_foundry/_canonical/canonical-registry.json"
        ),
    }


def _derived_superseded_values() -> set[str]:
    """Canonical values that receipts record and the tree no longer produces.

    Derived, not read from the registry. This is what closes the bypass a review
    demonstrated: with a hand-maintained value list, deleting one entry hid every
    dependent that asserted it. Here the values come from the receipts themselves
    compared against a freshly recomputed projection, so a value cannot be
    removed from consideration by editing the registry.
    """
    live = _live_canonical_values()
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    key in CANONICAL_VALUE_KEYS
                    and isinstance(value, str)
                    and value.startswith("sha256:")
                    and value not in live
                ):
                    found.add(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in _standing_receipts():
        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
    return found


def _standing_receipts() -> list[Path]:
    """Receipts that still make a live claim, not the whole attempt history.

    An earlier attempt's receipt records that attempt's own state at its own
    time; a later attempt supersedes it by construction. Marking those
    INVALIDATED would flood the registry with history and dilute the signal
    until nobody reads it. What the downstream-invalidation invariant is about
    is evidence that is *still standing* — the latest attempt of each package, plus package-level reports —
    so only those are derived from.
    """
    latest: dict[str, Path] = {}
    loose: list[Path] = []
    for path in sorted((repo_root() / "artifacts").rglob("*.json")):
        if path.name in EXCLUDED_NAMES:
            continue
        parts = path.relative_to(repo_root()).parts
        if len(parts) >= 5 and parts[1] == "work_packages" and parts[3] == "attempts":
            latest.setdefault(parts[2], path)
        else:
            loose.append(path)
    standing: list[Path] = list(loose)
    for package in sorted(
        {
            path.relative_to(repo_root()).parts[2]
            for path in (repo_root() / "artifacts" / "work_packages").rglob("*.json")
            if len(path.relative_to(repo_root()).parts) >= 5
            and path.relative_to(repo_root()).parts[3] == "attempts"
        }
    ):
        attempts_root = (
            repo_root() / "artifacts" / "work_packages" / package / "attempts"
        )
        # Only a directory that actually holds receipts counts as standing. A
        # review demoted a package's real receipts out of the derivation by
        # creating one EMPTY newer attempt directory, after which the values it
        # uniquely carried could be dropped from the registry unnoticed.
        directories = sorted(
            (
                entry
                for entry in attempts_root.iterdir()
                if entry.is_dir() and any(entry.rglob("*.json"))
            ),
            key=lambda entry: entry.name,
        )
        if directories:
            standing.extend(
                path
                for path in sorted(directories[-1].rglob("*.json"))
                if path.name not in EXCLUDED_NAMES
            )
    return standing


#: Where a superseded canonical value can come to rest. Scanning only
#: ``artifacts/`` was not enough: a review found five shipped cross-language
#: projections under ``web/``, ``packages/`` and ``python/`` still embedding a
#: pre-amendment schema digest, two of them sealed-pinned and byte-unchanged so
#: the pin gate passed them. That is this gate's own failure class surviving one
#: directory outside its scan, so the scan follows the value instead.
DEPENDENT_ROOTS = (
    Path("artifacts"),
    Path("web/src/generated"),
    Path("packages/contracts/src/generated"),
    Path("python/epistemic_foundry/contracts"),
    Path("build/v4_b05"),
)

#: Text formats a projection is emitted in. A digest embedded in TypeScript is
#: no less stale than one embedded in JSON.
DEPENDENT_SUFFIXES = (".json", ".ts", ".mjs", ".py", ".md", ".log", ".txt", ".xml")


def _artifacts_asserting(values: set[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    bare = {value.split(":", 1)[-1]: value for value in values}
    for root in DEPENDENT_ROOTS:
        directory = repo_root() / root
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in DEPENDENT_SUFFIXES:
                continue
            if path.name in EXCLUDED_NAMES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            stale = sorted(value for digest, value in bare.items() if digest in text)
            if stale:
                found[path.relative_to(repo_root()).as_posix()] = stale
    return found


def test_the_invalidation_status_is_the_taxonomy_term() -> None:
    """Use the vocabulary the repository already defines, not a new word.

    ``CapabilityStatus``, not ``ExitStatus``. Both define ``INVALIDATED`` and
    both stringify identically, so nothing broke — but `docs/status_taxonomy.md`
    places INVALIDATED under capability status and warns that work-package
    outcomes must not be substituted for capability states, and the registry's
    own ``status_meaning`` quotes the capability definition. A review caught the
    test named for using the right vocabulary using the wrong one of the two.
    """
    assert _registry()["status"] == CapabilityStatus.INVALIDATED


def test_no_superseded_value_can_be_hidden_by_editing_the_registry() -> None:
    """Close the bypass: the value list must not be the registry's own word.

    A review dropped one entry from ``superseded_values`` and every dependent
    receipt asserting it became invisible while the suite still passed. The
    derivation below does not consult the registry at all, so a value that
    receipts record and the tree no longer produces is found regardless.
    """
    declared = {str(entry["value"]) for entry in _registry()["superseded_values"]}
    derived = _derived_superseded_values()
    undeclared = sorted(derived - declared)
    assert not undeclared, (
        "canonical values are recorded by receipts, are no longer produced by "
        f"the tree, and are not declared superseded: {undeclared}"
    )


def test_the_invalidation_cites_an_authority_decision() -> None:
    decision_id = str(_registry().get("invalidated_by") or "").strip()
    path = (
        repo_root()
        / "artifacts"
        / "authority_decisions"
        / f"{decision_id}.human-decision.json"
    )
    assert path.is_file(), (
        f"the invalidation cites {decision_id!r}, which resolves to no decision "
        "record; an invalidation asserted on nobody's authority is just an opinion"
    )


def test_every_dependent_receipt_is_declared_invalidated() -> None:
    """The core invariant: no artifact may assert a superseded value silently."""
    declared = {row["receipt"] for row in _registry()["receipts"]}
    live = _artifacts_asserting(_superseded_values() | _derived_superseded_values())
    undeclared = sorted(set(live) - declared)
    assert not undeclared, (
        "artifacts assert a canonical value that a supersession retired, but are "
        f"not declared INVALIDATED: {undeclared[:10]}"
    )


def test_no_declared_receipt_is_stale_cover() -> None:
    """An entry that no longer asserts a superseded value must not linger.

    Same reasoning as the dormant-waiver check on the supersession registry: an
    exemption kept past its cause is cover for the next drift.
    """
    live = _artifacts_asserting(_superseded_values())
    stale_entries = sorted(
        row["receipt"] for row in _registry()["receipts"] if row["receipt"] not in live
    )
    assert not stale_entries, (
        "invalidation entries name artifacts that no longer assert a superseded "
        f"value and must be removed: {stale_entries[:10]}"
    )


def test_each_declared_supersession_is_true_of_the_live_projection() -> None:
    """Do not take the registry's word for what is retired — recompute it.

    A registry that declares a value superseded when it is still current would
    mark live evidence INVALIDATED, which is as damaging as leaving stale
    evidence valid. Both halves are checked against the tree: the retired value
    must no longer be produced, and the named replacement must be.
    """
    from scripts.build.canonical_registry.materialize import build_registry_document

    manifest, _ = build_registry_document(repo_root())
    live = {
        "canonical source bundle hash": manifest["source_bundle_hash"],
        "projected snapshot bundle hash": manifest["projected_snapshot_bundle_hash"],
        "canonical registry document hash": _digest(
            repo_root() / "src/epistemic_foundry/_canonical/canonical-registry.json"
        ),
        "retrieval-candidate projection file hash": _digest(
            repo_root()
            / "src/epistemic_foundry/_canonical/schemas/retrieval-candidate.schema.json"
        ),
    }
    wrong_replacement: list[str] = []
    not_actually_retired: list[str] = []
    for entry in _registry()["superseded_values"]:
        current = live.get(entry["what"])
        assert current is not None, f"unknown superseded subject: {entry['what']}"
        if entry["current_value"] != current:
            wrong_replacement.append(
                f"{entry['what']}: registry says {entry['current_value']}, tree has {current}"
            )
        if entry["value"] == current:
            not_actually_retired.append(entry["what"])
    assert not wrong_replacement, (
        "the invalidation registry names a replacement that is not what the tree "
        f"produces: {wrong_replacement}"
    )
    assert not not_actually_retired, (
        "the registry marks values INVALIDATED that are still current, which "
        f"voids live evidence: {not_actually_retired}"
    )


def test_the_registry_records_what_replaced_each_value() -> None:
    """ "Invalidated" is only actionable if the reader can find the current value."""
    declared = {
        entry["value"]: entry["current_value"]
        for entry in _registry()["superseded_values"]
    }
    incomplete: list[str] = []
    for row in _registry()["receipts"]:
        for assertion in row["asserts_superseded"]:
            if declared.get(assertion.get("value")) != assertion.get("current_value"):
                incomplete.append(f"{row['receipt']}:{assertion.get('value')}")
    assert not incomplete, (
        "invalidation entries do not point at the value that replaced them: "
        f"{incomplete[:10]}"
    )


def test_the_census_is_not_vacuous() -> None:
    """If the scan found nothing, every assertion above would be trivially true."""
    values = _superseded_values()
    assert values, "no superseded values are declared; the scan has nothing to do"
    assert _registry()["receipt_count"] == len(_registry()["receipts"])
    assert _registry()["receipts"], (
        "the invalidation registry is empty while supersessions exist; either the "
        "scan broke or the dependents were never enumerated"
    )
