"""unit_and_contract_tests — the happy paths hold their contracts.

Every gate produces a content-addressed receipt that re-derives its own
identifier and hash, and every receipt is a pure function of its inputs.  These
tests exercise the compositions the way a whole terminal release would: compose
the frozen sealed Z05 verdict, prove a declared bundle clean-extracts, hold every
source to the maturity floor, reconcile the composed-package accounting, and seal
the whole into one terminal verdict that never claims completion or
production-readiness.
"""

from __future__ import annotations

from epistemic_foundry.domain.hashing import hash_excluding

from v4_z05.zero_trust_release import UNSIGNED_STATUS, release_level_floor
from v4_z06.truthful_release import (
    CLEAN_EXTRACTION_PREFIX,
    COMPOSED_Z05_PREFIX,
    RELEASE_ACCOUNTING_PREFIX,
    TERMINAL_VERDICT_PREFIX,
    TRUTHFUL_MATURITY_PREFIX,
    compose_sealed_z05,
    reconcile_release_accounting,
    require_clean_extraction,
    require_truthful_maturity,
    seal_truthful_release,
)
from fixtures import (
    EXPECTED_PACKAGE_IDS,
    FLOOR,
    accounting_packages,
    clean_extraction_inputs,
    maturity_sources,
    seal_kwargs,
    z05_facts,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_clean_extraction_binds_a_byte_identical_bundle() -> None:
    receipt = require_clean_extraction(**clean_extraction_inputs())
    assert receipt["clean_extracted"] is True
    assert receipt["member_count"] == 3
    assert receipt["bundle_digest"].startswith("sha256:")
    assert receipt["signing_status"] == UNSIGNED_STATUS
    assert receipt["receipt_id"].startswith(CLEAN_EXTRACTION_PREFIX)
    assert _rederives(receipt)


def test_truthful_maturity_binds_sources_at_the_floor() -> None:
    receipt = require_truthful_maturity(sources=maturity_sources())
    assert receipt["release_level"] == FLOOR
    assert receipt["release_level"] == release_level_floor()
    assert receipt["completion_ready"] is False
    assert receipt["source_count"] == 2
    assert receipt["receipt_id"].startswith(TRUTHFUL_MATURITY_PREFIX)
    assert _rederives(receipt)


def test_release_accounting_reconciles_every_composed_package() -> None:
    receipt = reconcile_release_accounting(
        expected_package_ids=list(EXPECTED_PACKAGE_IDS),
        packages=accounting_packages(),
    )
    assert receipt["all_sealed"] is True
    assert receipt["expected_count"] == len(EXPECTED_PACKAGE_IDS)
    assert receipt["reconciled_count"] == len(EXPECTED_PACKAGE_IDS)
    assert receipt["receipt_id"].startswith(RELEASE_ACCOUNTING_PREFIX)
    assert _rederives(receipt)


def test_owned_conditional_is_admitted() -> None:
    packages = accounting_packages()
    packages[0]["conditionals"] = [{"id": "COND-1", "owner": "main-session-closeout"}]
    receipt = reconcile_release_accounting(
        expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
    )
    assert receipt["packages"][0]["conditional_count"] >= 0
    assert receipt["all_sealed"] is True


def test_compose_sealed_z05_binds_the_frozen_report_facts() -> None:
    receipt = compose_sealed_z05(z05=z05_facts())
    assert receipt["composed_package"] == "Z05"
    assert receipt["completion_ready"] is False
    assert receipt["z05_report_hash"].startswith("sha256:")
    assert receipt["receipt_id"].startswith(COMPOSED_Z05_PREFIX)
    assert _rederives(receipt)


def test_seal_binds_every_subreceipt_and_holds_the_maturity_floor() -> None:
    verdict = seal_truthful_release(**seal_kwargs())
    assert verdict["terminal"] is True
    assert verdict["release_passed"] is True
    assert verdict["completion_ready"] is False
    assert verdict["production_ready"] is False
    assert verdict["release_level"] == release_level_floor()
    assert verdict["signing_status"] == UNSIGNED_STATUS
    assert verdict["receipt_id"].startswith(TERMINAL_VERDICT_PREFIX)
    for field in (
        "z05_receipt_hash",
        "clean_extraction_receipt_hash",
        "maturity_receipt_hash",
        "accounting_receipt_hash",
    ):
        assert verdict[field].startswith("sha256:")
    assert _rederives(verdict)


def test_seal_is_a_pure_function_of_its_inputs() -> None:
    assert seal_truthful_release(**seal_kwargs()) == seal_truthful_release(
        **seal_kwargs()
    )
