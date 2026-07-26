"""Replay verification and source-integrity gating.

* EF4-I39: RunSpec, context, adapter/model, tools, receipts, policy, corpus, and
  prompts are sufficient to explain and compare a run. That sufficiency is only
  demonstrable by replay, so an unavailable pin makes the comparison
  `NOT_COMPARABLE` rather than a pass.
* EF4-I37: source access and license restrictions propagate through retrieval,
  evidence, export, and deletion. A document that may be read for extraction is
  not automatically exportable.
"""

from __future__ import annotations

from .replay import ReplayVerificationFailed, build_replay_report, replay_reproduced
from .integrity import (
    SourceAccessDenied,
    build_source_integrity_report,
    export_permitted,
)

__all__ = [
    "ReplayVerificationFailed",
    "SourceAccessDenied",
    "build_replay_report",
    "build_source_integrity_report",
    "export_permitted",
    "replay_reproduced",
]
