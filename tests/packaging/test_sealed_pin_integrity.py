"""Sealed product-file attestations must reproduce, or the drift must be declared.

A sealed RAH attempt records, in ``write_scope.product_file_hashes``, the hash of
every product file it wrote. Nothing in the harness ever re-checks those hashes
against the working tree — the seal was verified once, at seal time, and then no
consumer looked again. That leaves an entire class of change invisible: an edit
to a file some earlier attempt attested can land, pass every other gate, and
leave the repository asserting a hash it no longer has.

The gap is not that files must never change. Sealed attempts are history and a
later authorized change is allowed to move a file the seal recorded. The gap is
that the divergence was *silent*. This gate makes it declared:

* a pinned file that still matches its seal needs no entry;
* a pinned file that has moved must be covered by an entry in
  ``artifacts/work_packages/pin-supersessions.json`` naming the sealing attempt,
  both hashes, and why the change was authorized;
* an entry covers exactly one transition. It names the hash the file must have
  *now*, so a second change to the same file stops matching and this gate fires
  again rather than being permanently waived;
* an entry that no longer applies is itself a failure, so the registry cannot
  accumulate dormant cover for drift that has not happened yet;
* deleting a pinned product file is never a supersession.

The scan is also pinned against becoming vacuous. A census that silently found
nothing would make every assertion here trivially true, which is the same
failure mode this file exists to close.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from epistemic_foundry.contracts import repo_root

#: Sealed attempts present today. Seals are append-only, so this may rise and
#: must never fall; a drop means the scan stopped seeing the ledger. Was 180
#: while the scan globbed only ``*/attempts/*/report.json`` and missed 45 sealed
#: package-level reports, one of which already carries product pins.
MINIMUM_SEALED_ATTEMPTS = 225

#: Individual (file, attempt) attestations covered by the scan, same reasoning.
MINIMUM_PINNED_ASSERTIONS = 819

REGISTRY_PATH = Path("artifacts/work_packages/pin-supersessions.json")

#: The exact set of attestations known to exist. A count alone is not an
#: identity check: a review demonstrated the bypass by deleting one pin, adding
#: a decoy pin of equal count, and then editing the unpinned file freely. The
#: census below therefore compares sets, so a pin cannot be removed at all.
CENSUS_PATH = Path("artifacts/work_packages/pin-census.json")

REQUIRED_ENTRY_FIELDS = (
    "path",
    "sealed_by",
    "sealed_hash",
    "superseding_hash",
    "reason_code",
    "reason_text",
    "authorized_by",
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sealed(report: dict) -> bool:
    state = report.get("rah_state")
    if isinstance(state, dict):
        return bool(state.get("core_evidence_id"))
    if isinstance(state, list):
        return bool(state)
    return False


def _sealed_pins() -> list[tuple[str, str, str]]:
    """Every ``(attempt_id, relative_path, sealed_hash)`` a sealed attempt asserts."""
    pins: list[tuple[str, str, str]] = []
    for report_path in sorted(
        repo_root().glob("artifacts/work_packages/**/report.json")
    ):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(report, dict) or not _is_sealed(report):
            continue
        scope = report.get("write_scope")
        if not isinstance(scope, dict):
            continue
        hashes = scope.get("product_file_hashes")
        if not isinstance(hashes, dict):
            continue
        attempt = report.get("attempt_id") or report_path.parent.as_posix()
        for relative, sealed_hash in hashes.items():
            pins.append((str(attempt), str(relative), str(sealed_hash)))
    return pins


def _sealed_attempt_count() -> int:
    count = 0
    for report_path in repo_root().glob("artifacts/work_packages/**/report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(report, dict) and _is_sealed(report):
            count += 1
    return count


def _registry() -> dict:
    path = repo_root() / REGISTRY_PATH
    assert path.is_file(), f"{REGISTRY_PATH} is missing; the gate cannot run open"
    return json.loads(path.read_text(encoding="utf-8"))


def _entries() -> list[dict]:
    entries = _registry().get("supersessions")
    assert isinstance(entries, list), "supersessions must be a list"
    return entries


def _entry_index() -> dict[tuple[str, str], dict]:
    return {(entry["sealed_by"], entry["path"]): entry for entry in _entries()}


def test_the_census_is_not_vacuous() -> None:
    """A scan that finds nothing would pass every other test in this file."""
    attempts = _sealed_attempt_count()
    pins = _sealed_pins()
    assert attempts >= MINIMUM_SEALED_ATTEMPTS, (
        f"sealed-attempt census fell to {attempts}, floor is "
        f"{MINIMUM_SEALED_ATTEMPTS}: the ledger scan is no longer seeing seals"
    )
    assert len(pins) >= MINIMUM_PINNED_ASSERTIONS, (
        f"pinned-assertion census fell to {len(pins)}, floor is "
        f"{MINIMUM_PINNED_ASSERTIONS}: sealed attestations are being dropped"
    )


def test_no_attestation_was_removed() -> None:
    """Counting is not identity: an erased pin must not be maskable by a decoy.

    The census floors above only require the *number* of attestations to hold,
    so deleting one pin and adding another leaves them satisfied while the file
    that lost its pin becomes editable with no gate at all. This compares the
    actual set, so removal is caught regardless of what replaces it.
    """
    baseline = json.loads((repo_root() / CENSUS_PATH).read_text(encoding="utf-8"))
    recorded = set(baseline["assertions"])
    live = {f"{attempt}|{relative}" for attempt, relative, _ in _sealed_pins()}
    removed = sorted(recorded - live)
    assert not removed, (
        "attestations recorded in the pin census are no longer made by any "
        f"sealed report: {removed[:10]}"
    )
    digest = hashlib.sha256("\n".join(sorted(recorded)).encode("utf-8")).hexdigest()
    assert baseline["assertions_sha256"] == "sha256:" + digest, (
        "the pin census list and its own digest disagree"
    )


def test_no_sealed_report_was_edited() -> None:
    """Close the cheapest bypass: rewriting the pin instead of declaring drift.

    Every check in this file reads ``write_scope.product_file_hashes`` out of a
    ``report.json`` that nothing protects. A review pointed out the consequence:
    editing one line of a sealed report is cheaper than adding a supersession
    entry, leaves no artifact, and is invisible to a gate that only compares
    product files. The registry raised the cost of the honest path while the
    dishonest one stayed free. Sealed reports never legitimately change, so
    pinning them costs nothing.
    """
    baseline = json.loads((repo_root() / CENSUS_PATH).read_text(encoding="utf-8"))
    recorded: dict[str, str] = baseline["sealed_report_hashes"]
    edited: list[str] = []
    removed: list[str] = []
    for relative, expected in recorded.items():
        path = repo_root() / relative
        if not path.is_file():
            removed.append(relative)
        elif _digest(path) != expected:
            edited.append(relative)
    assert not removed, f"sealed reports are missing: {removed[:10]}"
    assert not edited, (
        "sealed reports were modified after being recorded; a seal's own "
        f"attestation is not editable: {edited[:10]}"
    )


def test_pin_coverage_is_declared_and_does_not_shrink() -> None:
    """State the gate's reach. A gate that reads comprehensive and is not is worse."""
    coverage = json.loads((repo_root() / CENSUS_PATH).read_text(encoding="utf-8"))[
        "coverage"
    ]
    live = len({relative for _, relative, _ in _sealed_pins()})
    assert live >= coverage["pinned_distinct_paths"], (
        f"pinned path coverage fell from {coverage['pinned_distinct_paths']} to {live}"
    )
    assert coverage["pinned_fraction_percent"] < 100, (
        "the census claims total coverage; it does not have it, and claiming so "
        "is the overclaim this file exists to prevent"
    )


def test_no_pinned_product_file_was_deleted() -> None:
    """Removal is not a supersession; a seal may not point at nothing."""
    absent = sorted(
        {
            f"{attempt}:{relative}"
            for attempt, relative, _ in _sealed_pins()
            if not (repo_root() / relative).is_file()
        }
    )
    assert not absent, f"sealed attempts pin files that no longer exist: {absent}"


def test_every_divergence_from_a_seal_is_declared() -> None:
    """The core invariant: drift is allowed, silent drift is not."""
    index = _entry_index()
    undeclared: list[str] = []
    mismatched: list[str] = []

    for attempt, relative, sealed_hash in _sealed_pins():
        path = repo_root() / relative
        if not path.is_file():
            continue
        current = _digest(path)
        if current == sealed_hash:
            continue
        entry = index.get((attempt, relative))
        if entry is None:
            undeclared.append(f"{attempt}:{relative}")
            continue
        if entry["sealed_hash"] != sealed_hash:
            mismatched.append(
                f"{attempt}:{relative} declares sealed_hash "
                f"{entry['sealed_hash']} but the seal records {sealed_hash}"
            )
        elif entry["superseding_hash"] != current:
            mismatched.append(
                f"{attempt}:{relative} was superseded again: the registry expects "
                f"{entry['superseding_hash']}, the tree has {current}"
            )

    assert not undeclared, (
        "product files diverge from a sealed attestation with no supersession "
        f"entry: {undeclared}"
    )
    assert not mismatched, "supersession entries no longer describe the tree: " + (
        "; ".join(mismatched)
    )


def test_no_supersession_entry_is_dormant() -> None:
    """An exemption for drift that has not happened is cover for future drift."""
    dormant: list[str] = []
    for entry in _entries():
        path = repo_root() / entry["path"]
        if not path.is_file():
            dormant.append(f"{entry['sealed_by']}:{entry['path']} (file absent)")
            continue
        if _digest(path) == entry["sealed_hash"]:
            dormant.append(
                f"{entry['sealed_by']}:{entry['path']} (still matches its seal)"
            )
    assert not dormant, (
        "supersession entries no longer apply and must be removed rather than "
        f"left as standing cover: {dormant}"
    )


def test_every_supersession_entry_names_a_real_pin() -> None:
    """The registry may only waive attestations that actually exist."""
    real = {(attempt, relative) for attempt, relative, _ in _sealed_pins()}
    phantom = sorted(
        f"{entry['sealed_by']}:{entry['path']}"
        for entry in _entries()
        if (entry["sealed_by"], entry["path"]) not in real
    )
    assert not phantom, (
        f"supersession entries reference attestations no seal makes: {phantom}"
    )


def test_every_waiver_resolves_to_a_recorded_authority_decision() -> None:
    """A justification is not an authorization until something can check it.

    ``authorized_by`` began as free text, and a review showed what that is worth:
    one entry cited ``SPEC_GAP-SOURCE-LOCATOR-PAGE closure``, an identifier that
    existed nowhere in the repository except the waiver it was supposed to
    justify, and another cited ``primary-session integrity correction`` — the
    author authorizing its own work, which `manifests/role_registry.yaml`
    forbids. Waiving a hash attestation over sealed evidence is a stronger act
    than the package-marker exceptions that already carry HumanDecision records,
    so it is held to the same evidence.
    """
    decisions_root = repo_root() / "artifacts" / "authority_decisions"
    unresolved: list[str] = []
    uncovered: list[str] = []

    for entry in _entries():
        decision_id = str(entry.get("authorized_by") or "").strip()
        path = decisions_root / f"{decision_id}.human-decision.json"
        if not path.is_file():
            unresolved.append(f"{entry['path']} -> {decision_id!r}")
            continue
        decision = json.loads(path.read_text(encoding="utf-8"))
        affected = [str(item) for item in decision.get("affected_artifact_ids") or []]
        covered = any(
            entry["path"] == item
            or (item.endswith("**") and entry["path"].startswith(item[:-2]))
            for item in affected
        )
        if not covered:
            uncovered.append(f"{entry['path']} not in {decision_id}")

    assert not unresolved, (
        "supersession entries cite an authorization that does not exist under "
        f"artifacts/authority_decisions/: {unresolved}"
    )
    assert not uncovered, (
        "supersession entries cite a decision that does not name the waived "
        f"path in affected_artifact_ids: {uncovered}"
    )


def test_cited_authority_decisions_are_self_consistent() -> None:
    """A decision whose own hash does not verify cannot authorize anything."""
    decisions_root = repo_root() / "artifacts" / "authority_decisions"
    broken: list[str] = []
    for decision_id in sorted({entry["authorized_by"] for entry in _entries()}):
        path = decisions_root / f"{decision_id}.human-decision.json"
        decision = json.loads(path.read_text(encoding="utf-8"))
        body = {key: value for key, value in decision.items() if key != "decision_hash"}
        digest = hashlib.sha256(
            json.dumps(
                body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        if decision.get("decision_hash") != "sha256:" + digest:
            broken.append(decision_id)
    assert not broken, (
        f"authority decisions whose decision_hash does not verify: {broken}"
    )


@pytest.mark.parametrize("field", REQUIRED_ENTRY_FIELDS)
def test_supersession_entries_are_fully_justified(field: str) -> None:
    """A waiver without a stated reason is an undocumented exception."""
    incomplete = [
        entry.get("path", "<no path>")
        for entry in _entries()
        if not str(entry.get(field) or "").strip()
    ]
    assert not incomplete, f"supersession entries missing {field}: {incomplete}"


def test_supersession_entries_are_unique() -> None:
    """Two entries for one attestation would let either one silently win."""
    keys = [(entry["sealed_by"], entry["path"]) for entry in _entries()]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert not duplicates, f"duplicate supersession entries: {duplicates}"


def test_the_declared_limitation_is_still_declared() -> None:
    """An annotation that can be deleted silently is a comment, not evidence.

    The census admits in `pin-census.json` that it is self-certifying: its own
    digest hashes the list it certifies, so a consistent three-file edit passes.
    That admission is the honest part of this gate — and two reviews pointed out
    that nothing read it, so it could be removed and every check would still
    pass, leaving a gate that reads stronger than it is. This is what the whole
    file exists to prevent, so the admission is pinned like everything else.
    """
    census = json.loads((repo_root() / CENSUS_PATH).read_text(encoding="utf-8"))
    limitation = str(census.get("limitation") or "")
    assert limitation.strip(), (
        "pin-census.json no longer declares its self-certification limit; the "
        "limit did not go away, only the disclosure did"
    )
    for required in ("self-certifying", "three-file", "not tamper-proof"):
        assert required in limitation, (
            f"the declared limitation no longer states {required!r}; it must keep "
            "naming the exact attack it does not stop"
        )
