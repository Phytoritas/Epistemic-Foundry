"""Fixtures over the in-memory T02 lifecycle harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from harness import (
    ROOT,
    ApprovalRecord,
    FakeApprovalResolver,
    FakeExecutor,
    FakeIdempotencyStore,
    FakeIntentStore,
    FakeLeaseIssuer,
    FakePolicyEvaluator,
    FakeReceiptStore,
    FakeRevisionStore,
    Harness,
)

from epistemic_foundry.application.mcp_common import ToolService
from epistemic_foundry.application.mcp_mutating import (
    MutationHandler,
    build_mutating_registry,
    load_mutating_catalog,
)


@pytest.fixture
def catalog() -> Any:
    return load_mutating_catalog(ROOT)


@pytest.fixture
def build_harness(catalog: Any):
    def _build(
        *,
        approvals: Sequence[ApprovalRecord] = (),
        grant_capability: bool = True,
        executor: FakeExecutor | None = None,
        leases: FakeLeaseIssuer | None = None,
        revisions: Mapping[tuple[str, str], str | None] | None = None,
    ) -> Harness:
        policy_port = FakePolicyEvaluator(catalog, grant_capability=grant_capability)
        approval_port = FakeApprovalResolver(approvals)
        lease_port = leases or FakeLeaseIssuer()
        idempotency_port = FakeIdempotencyStore()
        revision_port = FakeRevisionStore(revisions)
        intent_port = FakeIntentStore()
        executor_port = executor or FakeExecutor()
        receipt_port = FakeReceiptStore()
        handler = MutationHandler(
            catalog,
            approvals=approval_port,
            executor=executor_port,
            idempotency=idempotency_port,
            intents=intent_port,
            leases=lease_port,
            policy=policy_port,
            receipts=receipt_port,
            revisions=revision_port,
        )
        return Harness(
            approvals=approval_port,
            catalog=catalog,
            executor=executor_port,
            idempotency=idempotency_port,
            intents=intent_port,
            leases=lease_port,
            policy=policy_port,
            receipts=receipt_port,
            revisions=revision_port,
            service=ToolService(
                catalog,
                build_mutating_registry(catalog, handler),
                clock=lambda: "2026-08-01T08:00:00Z",
            ),
        )

    return _build
