"""schema_and_type_check — the gate is bound to the sealed surfaces' contracts.

Behaviour tests drive the gate; this file checks the shape of what it publishes
and, more importantly, that every hash it binds is the *sealed surface's own*
hash rather than a second copy.  A composition gate that re-derived a snapshot,
holdout, boundary or evaluator hash from its own view would be duplicating the
authority it is supposed to compose (EF4-I22); binding the owning module's hash
byte-for-byte is what proves it did not.
"""

from __future__ import annotations

import pytest

from epistemic_foundry.domain.hashing import is_schema_digest
from epistemic_foundry.evidence.v4_k06 import (
    FINDING_CODES,
    VERSION_ID_PREFIX,
    bind_evidence_holdout_version,
)
from epistemic_foundry.evidence.v4_k06.gate import LeakageGateError, _fail
from fixtures import version_arguments


def test_every_finding_code_declares_a_non_empty_reason() -> None:
    assert FINDING_CODES
    for code, reason in FINDING_CODES.items():
        assert code == code.upper() and " " not in code, code
        assert isinstance(reason, str) and reason.strip(), code


def test_fail_refuses_an_undeclared_finding_code() -> None:
    # The gate can only refuse in a vocabulary it declares; an unknown code is
    # itself an INPUT_INVALID rather than a silent new refusal reason.
    with pytest.raises(LeakageGateError) as excinfo:
        _fail("NOT_A_DECLARED_CODE", "boom")
    assert excinfo.value.code == "INPUT_INVALID"


def test_the_bound_version_binds_each_sealed_surface_hash_verbatim() -> None:
    arguments = version_arguments()
    version = bind_evidence_holdout_version(**arguments)
    assert version["corpus_snapshot_hash"] == arguments["snapshot"]["snapshot_hash"]
    assert version["partition_hash"] == arguments["partition"]["partition_hash"]
    assert version["holdout_manifest_hash"] == arguments["holdout"]["manifest_hash"]
    assert version["holdout_id"] == arguments["holdout"]["holdout_id"]
    assert version["boundary_hash"] == arguments["boundary"]["boundary_hash"]
    assert version["evaluator_bundle_hash"] == arguments["firewall"].sealed_hash
    assert version["evaluator_id"] == arguments["firewall"].bundle_id


def test_the_version_identifier_and_hashes_are_canonical_digests() -> None:
    version = bind_evidence_holdout_version(**version_arguments())
    assert version["version_id"].startswith(VERSION_ID_PREFIX)
    assert is_schema_digest(version["version_hash"])
    for field in (
        "corpus_snapshot_hash",
        "partition_hash",
        "holdout_manifest_hash",
        "boundary_hash",
        "evaluator_bundle_hash",
    ):
        assert is_schema_digest(version[field]), field


def test_the_concealed_set_is_exactly_the_non_visible_partition() -> None:
    arguments = version_arguments()
    partition = arguments["partition"]
    version = bind_evidence_holdout_version(**arguments)
    concealed = set(version["concealed_document_ids"])
    assert concealed == (
        set(partition["hidden_document_ids"])
        | set(partition["ood_document_ids"])
        | set(partition["adversarial_document_ids"])
    )
    assert concealed.isdisjoint(set(version["visible_document_ids"]))


def test_the_concealed_handles_are_exactly_the_holdout_bound_handles() -> None:
    arguments = version_arguments()
    version = bind_evidence_holdout_version(**arguments)
    firewall = arguments["firewall"]
    handles = version["concealed_partition_handles"]
    # The gate's concealed handle set is the same set the firewall treats as
    # leakage-bound; neither is a restatement of the other.
    assert firewall.leakage_invalidates(handles) == sorted(handles)
