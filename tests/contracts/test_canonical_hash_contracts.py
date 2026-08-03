"""A canonical-hash block must be computable from the schema alone.

``x-canonical-hash`` and ``x-canonical-identity`` define digests that identifiers
are derived from — ``registration_id == 'DREG-' + lowercase_hex(registration_hash)``.
Two implementations that disagree about the preimage do not produce a detectably
wrong answer; they produce *different identities for the same document*, and
nothing downstream can tell that happened.

That makes under-specification, not miscomputation, the dangerous failure here.
``document-registration`` listed ``schema_id`` in its preimage while declaring no
such property. The value was never missing — the contract test injects the
schema's own ``$id`` for domain separation, and production substitutes the
constant ``DOCUMENT_REGISTRATION_SCHEMA_ID`` — but the *contract* said neither.
An independent implementer reading the schema would have looked for a
``schema_id`` property, not found one, and either errored or omitted the field,
and their registration_ids would silently disagree with this repository's.

Production does not read ``$id``; it hardcodes the same string in two files
(``ingest/registry/hash.py`` and ``migrations/contracts/``). They agree today,
and nothing made them agree, so the fork stays reachable through drift in either
copy. ``test_schema_id_constants_track_the_schema`` binds all three.

So the invariants checked here are about *closure*, not about values:

* every preimage field resolves — it is a declared property, or ``field_sources``
  says which schema keyword supplies it;
* ``field_sources`` may not shadow a real property, which would make the instance
  value silently unused;
* every declared property is classified as hashed or excluded, so a field added
  later cannot drift into the preimage, or out of it, without someone deciding.
  One exception is deliberate and must be read as such: a block may declare
  ``exclusion_policy: all_other_properties`` instead of enumerating, and under
  that policy a later-added property IS auto-excluded with nobody deciding. That
  is the required semantics for an identity digest, which must stay closed so
  adding a field does not change the identity of unchanged records — but it is
  an exception to the sentence above, not an instance of it;
* nothing is in both lists.

``excluded_fields`` naming a field that does not exist is deliberately allowed.
Those entries are forward guards — ``storage_locator`` is excluded before it
exists so that adding a mutable physical locator cannot quietly change an
identity. A typo cannot hide behind that leniency, because the field the typo was
meant to name then shows up as unclassified.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epistemic_foundry.contracts import repo_root

CANONICAL_BLOCKS = ("x-canonical-hash", "x-canonical-identity")

#: Canonical blocks present today. Blocks are only ever added, so this may rise
#: and must never fall; a drop means the scan stopped finding them and every
#: assertion below would pass vacuously.
MINIMUM_CANONICAL_BLOCKS = 8


#: Both the authoring schemas and the materialized projection the runtime
#: actually reads. Scanning only the authoring copies left the projection — the
#: one the registry loads — unchecked; they are byte-identical by construction,
#: which is a reason to verify it rather than a reason to assume it.
SCHEMA_ROOTS = (
    Path("schemas"),
    Path("src/epistemic_foundry/_canonical/schemas"),
)


def _blocks() -> list[tuple[str, str, dict, dict]]:
    """``(schema_name, block_name, block, schema)`` for every canonical block."""
    found: list[tuple[str, str, dict, dict]] = []
    for root in SCHEMA_ROOTS:
        for path in sorted((repo_root() / root).glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            for name in CANONICAL_BLOCKS:
                block = schema.get(name)
                if isinstance(block, dict):
                    found.append(
                        (f"{root.as_posix()}/{path.name}", name, block, schema)
                    )
    return found


def _identify(entry: tuple[str, str, dict, dict]) -> str:
    return f"{entry[0]}::{entry[1]}"


BLOCKS = _blocks()


def test_the_scan_is_not_vacuous() -> None:
    assert len(BLOCKS) >= MINIMUM_CANONICAL_BLOCKS, (
        f"canonical-block census fell to {len(BLOCKS)}, floor is "
        f"{MINIMUM_CANONICAL_BLOCKS}: the schema scan is no longer finding them"
    )


@pytest.mark.parametrize("entry", BLOCKS, ids=_identify)
def test_every_preimage_field_resolves(entry: tuple[str, str, dict, dict]) -> None:
    """An unresolvable preimage field is an identity fork waiting to happen."""
    schema_name, block_name, block, schema = entry
    properties = set(schema.get("properties") or {})
    sources = block.get("field_sources") or {}
    unresolvable = [
        field
        for field in block.get("preimage_fields") or []
        if field not in properties and field not in sources
    ]
    assert not unresolvable, (
        f"{schema_name}::{block_name} hashes fields that are neither declared "
        f"properties nor mapped by field_sources: {unresolvable}. Two conformant "
        "implementations would disagree on the digest, and therefore on the id."
    )


@pytest.mark.parametrize("entry", BLOCKS, ids=_identify)
def test_field_sources_are_well_formed(entry: tuple[str, str, dict, dict]) -> None:
    """A mapping must be needed, must be used, and must point at something real."""
    schema_name, block_name, block, schema = entry
    sources = block.get("field_sources")
    if sources is None:
        return
    assert isinstance(sources, dict), f"{schema_name}::{block_name} field_sources"

    properties = set(schema.get("properties") or {})
    preimage = list(block.get("preimage_fields") or [])

    shadowing = sorted(set(sources) & properties)
    assert not shadowing, (
        f"{schema_name}::{block_name} maps {shadowing} through field_sources while "
        "also declaring them as properties, so the instance value would be "
        "silently discarded"
    )

    unused = sorted(set(sources) - set(preimage))
    assert not unused, (
        f"{schema_name}::{block_name} maps {unused} through field_sources but does "
        "not hash them; a mapping nobody uses is a claim nobody checks"
    )

    dangling = sorted(
        field for field, keyword in sources.items() if keyword not in schema
    )
    assert not dangling, (
        f"{schema_name}::{block_name} resolves {dangling} from schema keywords "
        "that this schema does not define"
    )


@pytest.mark.parametrize("entry", BLOCKS, ids=_identify)
def test_every_property_is_classified(entry: tuple[str, str, dict, dict]) -> None:
    """A field nobody classified is a field nobody decided about."""
    schema_name, block_name, block, schema = entry
    if "excluded_fields" not in block:
        # Omitting the list used to skip this test, which is how
        # retrieval-candidate::x-canonical-identity kept 34 properties
        # unclassified while the file claimed to forbid exactly that. A block
        # may decline to enumerate, but it may not decline to decide.
        policy = block.get("exclusion_policy")
        assert policy == "all_other_properties", (
            f"{schema_name}::{block_name} declares neither excluded_fields nor "
            "an exclusion_policy, so which properties affect the digest is "
            "undefined and this check would have silently skipped"
        )
        return
    properties = set(schema.get("properties") or {})
    preimage = set(block.get("preimage_fields") or [])
    excluded = set(block.get("excluded_fields") or [])
    unclassified = sorted(properties - preimage - excluded)
    assert not unclassified, (
        f"{schema_name}::{block_name} leaves {unclassified} neither hashed nor "
        "excluded, so whether they affect identity is undefined"
    )


@pytest.mark.parametrize("entry", BLOCKS, ids=_identify)
def test_no_field_is_both_hashed_and_excluded(
    entry: tuple[str, str, dict, dict],
) -> None:
    schema_name, block_name, block, _ = entry
    overlap = sorted(
        set(block.get("preimage_fields") or [])
        & set(block.get("excluded_fields") or [])
    )
    assert not overlap, (
        f"{schema_name}::{block_name} both hashes and excludes {overlap}; the "
        "contract contradicts itself and either reading is defensible"
    )


def test_schema_id_constants_track_the_schema() -> None:
    """Three copies of one identity string must not be free to drift apart.

    ``field_sources`` says ``schema_id`` resolves from the schema's ``$id``, but
    production hardcodes it. Equal values with no binding is not agreement, it is
    a coincidence that holds until someone edits one file.
    """
    import importlib.util

    schema = json.loads(
        (repo_root() / "schemas" / "document-registration.schema.json").read_text(
            encoding="utf-8"
        )
    )
    declared = schema["$id"]
    assert schema["x-canonical-hash"]["field_sources"]["schema_id"] == "$id"

    from epistemic_foundry.ingest.registry.hash import DOCUMENT_REGISTRATION_SCHEMA_ID

    assert DOCUMENT_REGISTRATION_SCHEMA_ID == declared, (
        "ingest/registry/hash.py substitutes a schema_id that no longer matches "
        f"the schema $id: {DOCUMENT_REGISTRATION_SCHEMA_ID!r} != {declared!r}"
    )

    migration_path = (
        repo_root() / "migrations" / "contracts" / "document_registration_migration.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_document_registration_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DOCUMENT_REGISTRATION_SCHEMA_ID == declared, (
        "the migration's schema_id no longer matches the schema $id: "
        f"{module.DOCUMENT_REGISTRATION_SCHEMA_ID!r} != {declared!r}"
    )


@pytest.mark.parametrize("entry", BLOCKS, ids=_identify)
def test_preimage_order_is_explicit_and_unique(
    entry: tuple[str, str, dict, dict],
) -> None:
    """A repeated field would be canonicalised away and change the digest."""
    schema_name, block_name, block, _ = entry
    preimage = list(block.get("preimage_fields") or [])
    assert preimage, f"{schema_name}::{block_name} declares an empty preimage"
    duplicates = sorted({field for field in preimage if preimage.count(field) > 1})
    assert not duplicates, (
        f"{schema_name}::{block_name} lists {duplicates} more than once"
    )
