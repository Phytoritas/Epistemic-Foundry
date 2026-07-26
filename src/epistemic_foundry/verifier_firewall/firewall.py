"""Evaluator sealing, holdout access control, and leakage invalidation.

Contract sources: `schemas/evaluator-bundle.schema.json`,
`schemas/holdout-manifest.schema.json`, `schemas/leakage-audit.schema.json`.

Design decisions worth stating:

* The bundle digest is computed over the bundle's semantic content, so any edit
  to metrics, evaluators, holdout binding, or policy changes the digest. Drift
  is therefore detectable without trusting a version label.
* `readable_by_candidates=True` or `mutable_during_run=True` is refused at seal
  time. A bundle that a candidate can read or mutate is not a firewall; catching
  it later would mean the run already produced contaminated comparisons.
* Access checks are default-deny over an explicit principal list, and a
  candidate-generating role is denied even when it appears on that list. A
  misconfigured allowlist must not become a capability.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Roles that propose candidates. They may never read hidden or OOD material,
#: because a generator that can see the holdout can fit it.
CANDIDATE_GENERATING_ROLES = frozenset(
    {
        "hypothesis_mutator",
        "prompt_genome_auditor",
        "experiment_evolver",
        "challenge_evolver",
        "candidate_generator",
        "evolution_proposer",
        "search_backend",
    }
)


class EvaluatorDrift(RuntimeError):
    """A sealed evaluator bundle changed during a run."""


class HoldoutAccessDenied(PermissionError):
    """A principal requested holdout access it does not hold."""


class FirewallRefusal(ValueError):
    """A bundle or manifest violates the firewall contract at seal time."""


def build_holdout_manifest(
    *,
    dataset_or_fixture_ids: Sequence[str],
    split_strategy: str,
    selection_cutoff: str,
    access_principal_ids: Sequence[str],
    unblinding_policy: str,
    rotation_policy: str,
    candidate_access: str = "NONE",
    holdout_manifest_id: str | None = None,
) -> dict[str, Any]:
    """Seal a holdout manifest.

    `candidate_access` defaults to `NONE`; `AGGREGATE_ONLY` and `METADATA_ONLY`
    exist in the schema for qualified reporting paths, but raw access is never
    representable.
    """
    if not dataset_or_fixture_ids:
        raise FirewallRefusal("a holdout manifest must bind at least one dataset or fixture")
    manifest: dict[str, Any] = {
        "holdout_manifest_id": holdout_manifest_id or new_id("HM"),
        "dataset_or_fixture_ids": list(dataset_or_fixture_ids),
        "split_strategy": split_strategy,
        "selection_cutoff": selection_cutoff,
        "access_principal_ids": list(access_principal_ids),
        "candidate_access": candidate_access,
        "unblinding_policy": unblinding_policy,
        "rotation_policy": rotation_policy,
    }
    manifest["manifest_hash"] = hash_excluding(manifest, "manifest_hash")
    validate_artifact("holdout-manifest", manifest)
    return manifest


def build_evaluator_bundle(
    *,
    version: str,
    evaluator_artifact_ids: Sequence[str],
    metric_ids: Sequence[str],
    holdout_manifest_id: str,
    environment_manifest_id: str,
    policy_bundle_id: str,
    metamorphic_test_ids: Sequence[str] = (),
    challenge_set_ids: Sequence[str] = (),
    evaluator_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Seal an evaluator bundle as candidate-unreadable and run-immutable."""
    bundle: dict[str, Any] = {
        "evaluator_bundle_id": evaluator_bundle_id or new_id("EB"),
        "version": version,
        "evaluator_artifact_ids": list(evaluator_artifact_ids),
        "metric_ids": list(metric_ids),
        "holdout_manifest_id": holdout_manifest_id,
        "environment_manifest_id": environment_manifest_id,
        "policy_bundle_id": policy_bundle_id,
        "metamorphic_test_ids": list(metamorphic_test_ids),
        "challenge_set_ids": list(challenge_set_ids),
        # Sealed by construction: the firewall refuses any other combination.
        "readable_by_candidates": False,
        "mutable_during_run": False,
    }
    bundle["bundle_hash"] = hash_excluding(bundle, "bundle_hash")
    validate_artifact("evaluator-bundle", bundle)
    return bundle


class VerifierFirewall:
    """Guards one run's evaluator bundle and its holdout."""

    def __init__(self, bundle: dict[str, Any], holdout: dict[str, Any]) -> None:
        validate_artifact("evaluator-bundle", bundle)
        validate_artifact("holdout-manifest", holdout)
        if bundle["readable_by_candidates"]:
            raise FirewallRefusal(
                "refusing a bundle marked readable_by_candidates: a readable evaluator can be fitted"
            )
        if bundle["mutable_during_run"]:
            raise FirewallRefusal(
                "refusing a bundle marked mutable_during_run: the current evaluator is immutable"
            )
        if bundle["holdout_manifest_id"] != holdout["holdout_manifest_id"]:
            raise FirewallRefusal(
                f"bundle binds holdout {bundle['holdout_manifest_id']!r} but manifest is "
                f"{holdout['holdout_manifest_id']!r}"
            )
        self._bundle = dict(bundle)
        self._holdout = dict(holdout)
        self._sealed_hash = str(bundle["bundle_hash"])

    @property
    def sealed_hash(self) -> str:
        return self._sealed_hash

    @property
    def bundle_id(self) -> str:
        return str(self._bundle["evaluator_bundle_id"])

    # -- immutability ----------------------------------------------------

    def assert_unchanged(self, bundle: dict[str, Any]) -> None:
        """Raise `EvaluatorDrift` when `bundle` differs from the sealed one.

        The digest is recomputed from content rather than read from the record,
        so a caller cannot hide an edit by also rewriting `bundle_hash`.
        """
        recomputed = hash_excluding(
            {key: value for key, value in bundle.items() if key != "bundle_hash"}, "bundle_hash"
        )
        if recomputed != self._sealed_hash:
            raise EvaluatorDrift(
                f"evaluator bundle drifted during the run: sealed {self._sealed_hash} != "
                f"recomputed {recomputed}"
            )

    def verify_self(self) -> None:
        """Confirm the sealed bundle still hashes to its recorded digest."""
        self.assert_unchanged(self._bundle)

    # -- access control --------------------------------------------------

    def may_read_holdout(self, principal_id: str, role: str) -> bool:
        """Default-deny holdout read check.

        A candidate-generating role is denied unconditionally: allowlist
        membership must not override the generator/verifier separation.
        """
        if role in CANDIDATE_GENERATING_ROLES:
            return False
        return principal_id in set(self._holdout["access_principal_ids"])

    def require_holdout_access(self, principal_id: str, role: str) -> None:
        """Raise `HoldoutAccessDenied` unless the principal holds access."""
        if not self.may_read_holdout(principal_id, role):
            reason = (
                "candidate-generating roles never read the hidden holdout"
                if role in CANDIDATE_GENERATING_ROLES
                else "principal is not on the holdout access list"
            )
            raise HoldoutAccessDenied(
                f"denied holdout access for {principal_id!r} as {role!r}: {reason}"
            )

    # -- leakage ---------------------------------------------------------

    def leakage_invalidates(self, leaked_ids: Iterable[str]) -> list[str]:
        """Return the holdout datasets touched by `leaked_ids`.

        A non-empty result means the affected comparisons are `INVALIDATED`.
        Callers must not convert this into a score adjustment.
        """
        bound = set(self._holdout["dataset_or_fixture_ids"])
        return sorted(bound.intersection(set(leaked_ids)))
