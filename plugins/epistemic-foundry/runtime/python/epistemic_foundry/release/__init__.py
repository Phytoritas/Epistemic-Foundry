"""Replay verification and source-integrity gating.

* EF4-I39: RunSpec, context, adapter/model, tools, receipts, policy, corpus, and
  prompts are sufficient to explain and compare a run. That sufficiency is only
  demonstrable by replay, so an unavailable pin makes the comparison
  `NOT_COMPARABLE` rather than a pass.
* EF4-I37: source access and license restrictions propagate through retrieval,
  evidence, export, and deletion. A document that may be read for extraction is
  not automatically exportable.
* EF4-I32/I35/I36: a shipped bundle carries reproducible build evidence, an SBOM,
  a manifest, clean extraction, and a derived signing status; the install matrix
  is a product acceptance test where `NOT_RUN` fails the gate; and remote
  messaging adapters are off by default and cannot execute commands or export raw
  evidence.
"""

from __future__ import annotations

from .replay import ReplayVerificationFailed, build_replay_report, replay_reproduced
from .integrity import (
    SourceAccessDenied,
    build_source_integrity_report,
    export_permitted,
)
from .provenance import (
    ProvenanceIncomplete,
    REQUIRED_INSTALL_CHECKS,
    RemoteAdapterRefused,
    build_release_provenance,
    build_remote_adapter_profile,
    install_acceptance_blockers,
    installability_is_demonstrated,
    release_is_shippable,
    signing_status_of,
)

__all__ = [
    "ProvenanceIncomplete",
    "REQUIRED_INSTALL_CHECKS",
    "RemoteAdapterRefused",
    "ReplayVerificationFailed",
    "SourceAccessDenied",
    "build_release_provenance",
    "build_remote_adapter_profile",
    "build_replay_report",
    "build_source_integrity_report",
    "export_permitted",
    "install_acceptance_blockers",
    "installability_is_demonstrated",
    "release_is_shippable",
    "replay_reproduced",
    "signing_status_of",
]
