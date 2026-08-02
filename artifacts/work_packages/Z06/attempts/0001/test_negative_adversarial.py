"""negative_and_adversarial_tests — every refusal fires under attack.

Each declared ``FINDING_CODES`` entry is provoked at least once, and the
adversarial cases are the ones this terminal gate exists to stop: a bundle member
that traverses out of the extraction root (zip-slip), an extraction that does not
match its declared digest (tamper), a surplus or missing member, a source that
overstates the maturity or claims completion or presents the bundle as
production-ready, a composed package that is not sealed or that claims completion,
an accounting that drops or invents a package, an unowned conditional, a composed
Z05 report that is not sealed, and a terminal verdict that tries to declare the
product complete or production-ready.  A refusal firing under the wrong code would
be as much a defect as no refusal at all, so every case asserts the exact code.
"""

from __future__ import annotations

import pytest

from v4_z06 import truthful_release as mod
from v4_z06.truthful_release import (
    compose_sealed_z05,
    reconcile_release_accounting,
    require_clean_extraction,
    require_truthful_maturity,
    seal_truthful_release,
)
from fixtures import (
    EXPECTED_PACKAGE_IDS,
    accounting_packages,
    build_checks,
    bundle_extraction,
    bundle_members,
    clean_extraction_inputs,
    maturity_source,
    maturity_sources,
    provenance_inputs,
    seal_kwargs,
    z05_facts,
)


def _code(caught: pytest.ExceptionInfo) -> str:
    return caught.value.code  # type: ignore[attr-defined]


# --- input integrity ----------------------------------------------------------


def test_empty_bundle_id_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(**clean_extraction_inputs(bundle_id=""))
    assert _code(caught) == "INPUT_INVALID"


def test_non_sequence_sources_are_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_truthful_maturity(sources={"not": "a-sequence"})  # type: ignore[arg-type]
    assert _code(caught) == "INPUT_INVALID"


# --- clean extraction ---------------------------------------------------------


def test_provenance_missing_clean_extraction_check_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(
            **clean_extraction_inputs(
                provenance_inputs=provenance_inputs(
                    checks=build_checks(clean_extraction="NOT_RUN")
                )
            )
        )
    assert _code(caught) == "CLEAN_EXTRACTION_PROVENANCE_REFUSED"


def test_zip_slip_member_is_refused() -> None:
    members = bundle_members()
    members[0]["path"] = "../../etc/passwd"
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(**clean_extraction_inputs(members=members))
    assert _code(caught) == "BUNDLE_MEMBER_UNSAFE_PATH"


def test_absolute_extracted_path_is_refused() -> None:
    extraction = bundle_extraction()
    extraction[0]["path"] = "C:/Windows/system32/evil.dll"
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(**clean_extraction_inputs(extracted=extraction))
    assert _code(caught) == "BUNDLE_MEMBER_UNSAFE_PATH"


def test_tampered_member_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(
            **clean_extraction_inputs(extracted=bundle_extraction(tamper=True))
        )
    assert _code(caught) == "BUNDLE_MEMBER_TAMPERED"


def test_surplus_extracted_member_is_refused() -> None:
    extraction = bundle_extraction()
    extraction.append({"path": "stowaway.txt", "content_hash": "sha256:" + "9" * 64})
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(**clean_extraction_inputs(extracted=extraction))
    assert _code(caught) == "BUNDLE_SURPLUS_MEMBER"


def test_missing_extracted_member_is_refused() -> None:
    extraction = bundle_extraction()[:-1]
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_clean_extraction(**clean_extraction_inputs(extracted=extraction))
    assert _code(caught) == "BUNDLE_MISSING_MEMBER"


# --- truthful maturity --------------------------------------------------------


def test_release_level_above_the_floor_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_truthful_maturity(
            sources=[maturity_source(release_level="PLUGIN_ALPHA")]
        )
    assert _code(caught) == "MATURITY_LEVEL_ABOVE_FLOOR"


def test_source_claiming_completion_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_truthful_maturity(sources=[maturity_source(completion_ready=True)])
    assert _code(caught) == "SOURCE_CLAIMS_COMPLETION"


def test_forbidden_production_ready_claim_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_truthful_maturity(
            sources=[
                maturity_source(claims=["the v4 plugin is production-ready today"])
            ]
        )
    assert _code(caught) == "FORBIDDEN_MATURITY_CLAIM"


def test_forbidden_signed_claim_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        require_truthful_maturity(
            sources=[maturity_source(claims=["the release bundle is signed"])]
        )
    assert _code(caught) == "FORBIDDEN_MATURITY_CLAIM"


# --- release accounting -------------------------------------------------------


def test_unsealed_composed_package_is_refused() -> None:
    packages = accounting_packages()
    packages[0]["status"] = "FAIL"
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        reconcile_release_accounting(
            expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
        )
    assert _code(caught) == "ACCOUNTING_PACKAGE_NOT_SEALED"


def test_composed_package_claiming_completion_is_refused() -> None:
    packages = accounting_packages()
    packages[0]["completion_ready"] = True
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        reconcile_release_accounting(
            expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
        )
    assert _code(caught) == "ACCOUNTING_PACKAGE_CLAIMS_COMPLETION"


def test_missing_composed_package_is_refused() -> None:
    packages = accounting_packages()[:-1]
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        reconcile_release_accounting(
            expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
        )
    assert _code(caught) == "ACCOUNTING_MISSING_PACKAGE"


def test_surplus_composed_package_is_refused() -> None:
    packages = accounting_packages()
    packages.append(
        {
            "package_id": "ZZZ",
            "status": packages[0]["status"],
            "completion_ready": False,
            "report_hash": "sha256:" + "0" * 64,
            "conditionals": [],
        }
    )
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        reconcile_release_accounting(
            expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
        )
    assert _code(caught) == "ACCOUNTING_SURPLUS_PACKAGE"


def test_unowned_conditional_is_refused() -> None:
    packages = accounting_packages()
    packages[0]["conditionals"] = [{"id": "COND-1", "owner": ""}]
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        reconcile_release_accounting(
            expected_package_ids=list(EXPECTED_PACKAGE_IDS), packages=packages
        )
    assert _code(caught) == "ACCOUNTING_UNOWNED_CONDITIONAL"


# --- composed Z05 -------------------------------------------------------------


def test_unsealed_composed_z05_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        compose_sealed_z05(z05=z05_facts(status="FAIL"))
    assert _code(caught) == "COMPOSED_Z05_NOT_SEALED"


def test_composed_z05_claiming_completion_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        compose_sealed_z05(z05=z05_facts(completion_ready=True))
    assert _code(caught) == "COMPOSED_Z05_CLAIMS_COMPLETION"


# --- terminal honesty ---------------------------------------------------------


def test_seal_claiming_completion_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        seal_truthful_release(**seal_kwargs(), completion_ready=True)
    assert _code(caught) == "TERMINAL_MATURITY_OVERCLAIM"


def test_seal_claiming_production_readiness_is_refused() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        seal_truthful_release(**seal_kwargs(), production_ready=True)
    assert _code(caught) == "TERMINAL_MATURITY_OVERCLAIM"


def test_seal_propagates_a_composed_gate_refusal() -> None:
    # A tampered bundle member fails the whole terminal seal, not just the
    # standalone clean-extraction gate.
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        seal_truthful_release(
            **seal_kwargs(
                clean_extraction_inputs=clean_extraction_inputs(
                    extracted=bundle_extraction(tamper=True)
                )
            )
        )
    assert _code(caught) == "BUNDLE_MEMBER_TAMPERED"


def test_seal_propagates_a_forbidden_maturity_claim() -> None:
    with pytest.raises(mod.TruthfulReleaseError) as caught:
        seal_truthful_release(
            **seal_kwargs(
                maturity_sources=[
                    *maturity_sources(),
                    maturity_source(claims=["v4 is generally available"]),
                ]
            )
        )
    assert _code(caught) == "FORBIDDEN_MATURITY_CLAIM"
