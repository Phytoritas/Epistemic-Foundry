"""Typed refusals shared by the T06 backend integration gate.

T05 already owns a refusal table for pinning, qualification and import.  T06
keeps its own rather than extending that one, and raises a different exception
type, so a caller can always tell which contract stopped a request: a
``AdapterGateError`` means the sealed T05 surface refused the inputs, and an
``IntegrationGateError`` means T06 refused the *lifecycle* the inputs describe.
The shape checks below are deliberately delegated to T05's helpers, so an
unusable identifier or an edited record still refuses under T05's code and
message rather than being re-wrapped into a second vocabulary that says the
same thing less precisely.

The one addition is time.  Every judgement this package makes about expiry is
made against a caller-supplied instant, never a clock, so ``require_instant``
refuses a timestamp that cannot be compared before any window is evaluated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ..v4_t05.findings import _fail as _refuse_at_t05
from ..v4_t05.findings import require_identifier

#: Every way this package refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "BACKEND_IDENTITY_MISMATCH": (
        "two records that must describe the same backend name different "
        "manifests, so a lifecycle, a fallback member or a disablement would "
        "be applied to a build it was never derived from"
    ),
    "DISABLED_BACKEND_STILL_SERVING": (
        "a request was routed to a backend at or after the instant it was "
        "disabled, so the disablement produced a record while the backend kept "
        "serving, which is the silent continuation the gate exists to stop"
    ),
    "FALLBACK_CAPABILITY_WIDENED": (
        "a fallback member declares a capability the primary member does not "
        "hold, or one the request did not ask for, so degrading would hand the "
        "caller more reach — network or authority — than the path it replaced"
    ),
    "FALLBACK_CHAIN_MALFORMED": (
        "the declared fallback chain does not terminate in the domain-neutral "
        "core, repeats a member, or places the core before the end, so the "
        "chain has no guaranteed terminal step and could run out of members"
    ),
    "FALLBACK_MEMBER_UNQUALIFIED": (
        "a declared fallback member carries no qualification chain of its own, "
        "or one whose verdict never permitted serving, so the chain would name "
        "a substitute that was never qualified to be one"
    ),
    "FALLBACK_UNRECORDED": (
        "a routing record serves from other than its primary member without an "
        "event naming the member it left and the trigger it left on, so the "
        "degradation happened but the audit trail cannot show that it did"
    ),
    "QUALIFICATION_CHAIN_BROKEN": (
        "a requalification does not reference the qualification record it "
        "replaces, references one it does not follow, or begins a chain at a "
        "later position, so a qualification would appear from nowhere"
    ),
    "QUALIFICATION_NOT_SERVING": (
        "the qualification that would authorize this request does not permit "
        "serving at the instant asked — it expired, was revoked, was replaced "
        "by a later record, or never carried a verdict that permits use"
    ),
    "QUALIFICATION_WINDOW_INVALID": (
        "a qualification's validity window does not open strictly before it "
        "closes, or a successor is issued before the record it replaces, so "
        "expiry could not be decided against any consistent ordering"
    ),
    "REVERIFICATION_UNMARKED": (
        "an in-flight imported run was not marked as requiring re-verification "
        "by the disablement that invalidated the backend it came from, so its "
        "results would keep being read as if the backend were still qualified"
    ),
    "TIMESTAMP_NOT_ABSOLUTE": (
        "a timestamp is not an offset-aware RFC 3339 instant, so two records "
        "could not be ordered against each other and 'expired' would be a "
        "judgement made against an ambiguous local reading"
    ),
}


class IntegrationGateError(ValueError):
    """A lifecycle, fallback or disablement request was refused.

    Deliberately not a subclass of T05's ``AdapterGateError``: the two answer
    different questions, and a test that catches one must not silently catch
    the other.
    """

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    """Refuse under a declared code, or refuse the refusal itself.

    An undeclared code is routed back through T05's guard rather than given a
    T06 code of its own, because "this package invented a finding" is an input
    problem, and T05 already owns the code that says so.
    """
    if code not in FINDING_CODES:
        _refuse_at_t05(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise IntegrationGateError(code, message, context)


def require_instant(value: object, label: str) -> datetime:
    """Refuse a timestamp that cannot be compared with another one.

    Every instant in this package is supplied by the caller.  A naive reading
    would compare unequal offsets as if they were the same moment, so the
    refusal happens here rather than at the point where a window is judged.
    """
    text = require_identifier(value, label)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        _fail(
            "TIMESTAMP_NOT_ABSOLUTE",
            f"{label} is not an RFC 3339 instant",
            {"label": label, "value": text},
        )
        raise  # pragma: no cover - _fail always raises
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        _fail(
            "TIMESTAMP_NOT_ABSOLUTE",
            f"{label} carries no UTC offset",
            {"label": label, "value": text},
        )
    return moment
