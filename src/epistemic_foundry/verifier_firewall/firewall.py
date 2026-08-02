"""Evaluator sealing, holdout access control, and leakage invalidation.

Contract sources: `schemas/evaluator-bundle.schema.json`,
`schemas/holdout-manifest.schema.json`, `schemas/leakage-audit.schema.json`.

Design decisions worth stating:

* The bundle digest is computed over the bundle's semantic content, so any edit
  to metrics, evaluators, holdout binding, or policy changes the digest. Drift
  is therefore detectable without trusting a version label.
* Candidate access or current-run mutation is refused at seal time. A bundle
  that a candidate can read or mutate is not a firewall; catching it later
  would mean the run already produced contaminated comparisons.
* Principal access is runtime policy input, not persisted holdout content.
  Checks are default-deny over that explicit input, and a candidate-generating
  role is denied even when it appears there. A misconfigured allowlist must not
  become a capability.
"""

from __future__ import annotations

from copy import deepcopy
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
    evaluator_id: str,
    split_strategy: str,
    public_partition_refs: Sequence[str],
    hidden_partition_handles: Sequence[str],
    ood_partition_handles: Sequence[str],
    adversarial_partition_handles: Sequence[str],
    content_hashes: Sequence[str],
    acl_policy_hash: str,
    log_redaction_policy: str,
    cache_isolation_policy: str,
    holdout_id: str | None = None,
    sealed_at: str | None = None,
) -> dict[str, Any]:
    """Seal the canonical holdout manifest from explicit immutable inputs.

    Hidden handles, content hashes, and the access/redaction policies are
    required rather than discovered from the current environment.  Candidate,
    mutation-model, prompt, and backend access are false by construction.
    """
    if not hidden_partition_handles:
        raise FirewallRefusal("a holdout manifest must bind at least one hidden partition handle")
    if not content_hashes:
        raise FirewallRefusal("a holdout manifest must bind at least one immutable content hash")
    timestamp = sealed_at or utc_now_iso()
    manifest: dict[str, Any] = {
        "holdout_id": holdout_id or new_id("HO"),
        "evaluator_id": evaluator_id,
        "split_strategy": split_strategy,
        "public_partition_refs": list(public_partition_refs),
        "hidden_partition_handles": list(hidden_partition_handles),
        "ood_partition_handles": list(ood_partition_handles),
        "adversarial_partition_handles": list(adversarial_partition_handles),
        "content_hashes": list(content_hashes),
        "acl_policy_hash": acl_policy_hash,
        "candidate_access": False,
        "mutation_model_access": False,
        "prompt_access": False,
        "backend_access": False,
        "log_redaction_policy": log_redaction_policy,
        "cache_isolation_policy": cache_isolation_policy,
        "unblinding_approval_required": True,
        "sealed_at": timestamp,
    }
    manifest["manifest_hash"] = hash_excluding(manifest, "manifest_hash")
    validate_artifact("holdout-manifest", manifest)
    return manifest


def build_evaluator_bundle(
    *,
    evaluator_version: str,
    code_artifact_id: str,
    code_hash: str,
    metric_contract_hash: str,
    environment_digest: str,
    dependency_lock_hash: str,
    data_contract_hash: str,
    policy_bundle_hash: str,
    qualification_report_id: str,
    holdout_manifest_id: str,
    evaluator_id: str | None = None,
    sealed_at: str | None = None,
) -> dict[str, Any]:
    """Seal an evaluator bundle as candidate-unreadable and run-immutable."""
    timestamp = sealed_at or utc_now_iso()
    bundle: dict[str, Any] = {
        "evaluator_id": evaluator_id or new_id("EVAL"),
        "evaluator_version": evaluator_version,
        "code_artifact_id": code_artifact_id,
        "code_hash": code_hash,
        "metric_contract_hash": metric_contract_hash,
        "environment_digest": environment_digest,
        "dependency_lock_hash": dependency_lock_hash,
        "data_contract_hash": data_contract_hash,
        "policy_bundle_hash": policy_bundle_hash,
        "qualification_report_id": qualification_report_id,
        "holdout_manifest_id": holdout_manifest_id,
        "sealed_at": timestamp,
        "immutable": True,
        "candidate_access": False,
        "mutation_allowed_for_current_run": False,
    }
    bundle["bundle_hash"] = hash_excluding(bundle, "bundle_hash")
    validate_artifact("evaluator-bundle", bundle)
    return bundle


class VerifierFirewall:
    """Guards one run's evaluator bundle and its holdout."""

    def __init__(
        self,
        bundle: dict[str, Any],
        holdout: dict[str, Any],
        *,
        holdout_read_principal_ids: Sequence[str],
    ) -> None:
        if bundle.get("candidate_access") is not False:
            raise FirewallRefusal(
                "refusing a bundle marked candidate_access: a readable evaluator can be fitted"
            )
        if (
            bundle.get("immutable") is not True
            or bundle.get("mutation_allowed_for_current_run") is not False
        ):
            raise FirewallRefusal(
                "refusing a mutable evaluator bundle: the current evaluator is immutable"
            )
        for access_field in (
            "candidate_access",
            "mutation_model_access",
            "prompt_access",
            "backend_access",
        ):
            if holdout.get(access_field) is not False:
                raise FirewallRefusal(
                    f"refusing holdout manifest with {access_field}=true"
                )
        validate_artifact("evaluator-bundle", bundle)
        validate_artifact("holdout-manifest", holdout)
        expected_bundle_hash = hash_excluding(bundle, "bundle_hash")
        if bundle["bundle_hash"] != expected_bundle_hash:
            raise FirewallRefusal(
                f"evaluator bundle hash mismatch: recorded {bundle['bundle_hash']} != "
                f"recomputed {expected_bundle_hash}"
            )
        expected_manifest_hash = hash_excluding(holdout, "manifest_hash")
        if holdout["manifest_hash"] != expected_manifest_hash:
            raise FirewallRefusal(
                f"holdout manifest hash mismatch: recorded {holdout['manifest_hash']} != "
                f"recomputed {expected_manifest_hash}"
            )
        if bundle["holdout_manifest_id"] != holdout["holdout_id"]:
            raise FirewallRefusal(
                f"bundle binds holdout {bundle['holdout_manifest_id']!r} but manifest is "
                f"{holdout['holdout_id']!r}"
            )
        if bundle["evaluator_id"] != holdout["evaluator_id"]:
            raise FirewallRefusal(
                f"bundle evaluator {bundle['evaluator_id']!r} does not match manifest evaluator "
                f"{holdout['evaluator_id']!r}"
            )
        # Keep an owned snapshot of the sealed records.  A shallow copy would
        # leave the holdout's handle lists aliased to caller-owned objects, so
        # mutating an input list after construction could silently change the
        # firewall's leakage boundary without changing the recorded manifest
        # hash.
        self._bundle = deepcopy(bundle)
        self._holdout = deepcopy(holdout)
        self._holdout_read_principal_ids = frozenset(holdout_read_principal_ids)
        self._sealed_hash = str(bundle["bundle_hash"])

    @property
    def sealed_hash(self) -> str:
        return self._sealed_hash

    @property
    def bundle_id(self) -> str:
        return str(self._bundle["evaluator_id"])

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
        return principal_id in self._holdout_read_principal_ids

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
        bound = set(self._holdout["hidden_partition_handles"])
        bound.update(self._holdout["ood_partition_handles"])
        bound.update(self._holdout["adversarial_partition_handles"])
        return sorted(bound.intersection(set(leaked_ids)))
