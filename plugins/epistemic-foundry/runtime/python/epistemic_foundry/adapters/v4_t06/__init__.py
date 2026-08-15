"""External-backend qualification and fallback integration gate (T06).

T05 sealed the question "may this backend be used at all?".  This package
answers the three questions that only appear once the answer is yes and the
system has to keep running afterwards: for how long, what happens instead when
it lapses, and what becomes of the work already in flight when it is turned
off.

The gate composes T05 rather than restating it.  Pinning, capability
qualification, the S05 executor binding and the imported-run boundary are
called, and their refusals are propagated unwrapped so a failure still names
the contract that made it.  What is added is duration, ordered substitution and
withdrawal — none of which T05 can express, and all of which an operator needs
before an optional backend can honestly be relied on.

It gates.  It does not run, score, promote or evaluate anything, and the
domain-neutral core it falls back to is the Foundry itself, unchanged.
"""

from __future__ import annotations

from .disable import (
    assert_not_serving_after_disable,
    assert_reverification_marked,
    disable_backend,
)
from .fallback import (
    FALLBACK_TRIGGER_CODE,
    MEMBER_FIELDS,
    NATIVE_CORE_MEMBER_ID,
    assert_fallback_recorded,
    backend_member,
    declare_fallback_chain,
    native_core_member,
    route_request,
)
from .findings import (
    FINDING_CODES,
    IntegrationGateError,
    require_instant,
)
from .qualification_lifecycle import (
    BINDING_FIELDS,
    STANDING_DEACTIVATED,
    STANDING_EXPIRED,
    STANDING_NOT_YET_ISSUED,
    STANDING_REPLACED,
    STANDING_REVOKED,
    STANDING_SERVING,
    STANDING_STATUS_NOT_USABLE,
    STANDINGS,
    WITHDRAWAL_KINDS,
    assert_may_serve,
    build_chain,
    open_qualification,
    requalify,
    standing,
    usable_statuses,
    verified_chain,
    withdraw_qualification,
)

__all__ = [
    "BINDING_FIELDS",
    "FALLBACK_TRIGGER_CODE",
    "FINDING_CODES",
    "MEMBER_FIELDS",
    "NATIVE_CORE_MEMBER_ID",
    "STANDINGS",
    "STANDING_DEACTIVATED",
    "STANDING_EXPIRED",
    "STANDING_NOT_YET_ISSUED",
    "STANDING_REPLACED",
    "STANDING_REVOKED",
    "STANDING_SERVING",
    "STANDING_STATUS_NOT_USABLE",
    "WITHDRAWAL_KINDS",
    "IntegrationGateError",
    "assert_fallback_recorded",
    "assert_may_serve",
    "assert_not_serving_after_disable",
    "assert_reverification_marked",
    "backend_member",
    "build_chain",
    "declare_fallback_chain",
    "disable_backend",
    "native_core_member",
    "open_qualification",
    "requalify",
    "require_instant",
    "route_request",
    "standing",
    "usable_statuses",
    "verified_chain",
    "withdraw_qualification",
]
