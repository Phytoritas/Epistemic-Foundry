"""Honest degraded UI and operator usability integration gate (U06).

U05 sealed the read-only projection of the Evolution Chamber's four surfaces —
the Pareto front, the M05 niche map, the candidate lineages and the Red Queen
challenge board — into deep-frozen, hash-re-derivable *view* records.  Each view
is correct alone, and a projection either succeeds or is *refused*: a tampered,
absent, drifted or malformed surface raises a :class:`ConsoleProjectionRefused`
carrying a finding code.  What had no owner was the operator's question: for a
whole console screen composed of several surfaces, which panels can be shown,
which cannot, and does the screen ever *overstate* what it knows?

This is that gate, and only that gate.  It **composes** the sealed U05
projection into an operator dashboard whose every panel resolves to one of the
four canonical honest-UI states (EF4-I23) — read from the module that owns them
(:mod:`epistemic_foundry.observability.result_state`), never named here
(EF4-I22).  A surface that projects cleanly and carries results is
``POPULATED``; a surface that projects, is current, and is genuinely empty is
``EMPTY_CONFIRMED``; a surface that projects but was built against a superseded
revision is ``DEGRADED``; and a surface that is **absent or that U05 refuses**
is ``UNAVAILABLE`` — carrying the U05 finding code as its reason.  The
distinction is the whole point: an upstream that cannot be trusted or derived is
*never* fabricated into a healthy panel and *never* silently defaulted into a
confirmed emptiness.  A backend failure that looked empty would tell an operator
that nothing exists when in fact nothing was read, and that is the one output
this gate exists to forbid.

It **grants no authority**: every panel and dashboard carries ``readonly`` and
``grants_authority`` markers that are always the same two values, and any
``authority_request`` — a caller asking the console to decide, select, promote
or expose a holdout — is refused before any surface is touched, exactly as U05
refuses it.  No candidate, model, prompt, backend or hook reaches an evaluator,
holdout or promotion surface through here.

It **overstates nothing**: a dashboard's ``complete`` flag is true only when
*every* requested surface is ``POPULATED``, and :func:`audit_dashboard_completeness`
independently recomputes that verdict from the panels a dashboard actually
embeds, so a record that claims completeness over a degraded or unavailable
panel is refused rather than believed.

Every decision resolves to an immutable, content-addressed receipt: two runs
over equal inputs produce byte-equal receipts.  Nothing here scores, promotes,
mutates its inputs, or reads a clock — the caller supplies ``created_at`` and the
identifier and hash are a pure function of the record's own content.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ...domain.hashing import (
    SHA256_PREFIX,
    hash_excluding,
    sha256_of_payload,
)
from ...observability.result_state import (
    ResultState,
    ResultStateViolation,
    require_honest_state,
)
from ..v4_u05 import (
    SURFACE_CHALLENGE_BOARD,
    SURFACE_LINEAGES,
    SURFACE_NICHE_MAP,
    SURFACE_PARETO_FRONT,
    ConsoleProjectionRefused,
    build_console_projection,
    declared_surfaces,
    require_view_identity,
)

#: Every way this gate refuses, and why the refusal exists.  A refusal whose
#: code is absent here is a bug rather than a decision, so :func:`_fail` checks
#: membership and every code below is exercised by the negative-and-adversarial
#: suite.  Honest *degradation* is not a refusal: a surface that cannot be shown
#: becomes a panel whose state says so, not an error.  These codes fire only when
#: the gate cannot even honestly represent what it was handed.
FINDING_CODES: dict[str, str] = {
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "compose a dashboard from something it never validated"
    ),
    "SURFACE_UNDECLARED": (
        "a panel was requested for a surface the sealed console does not project, "
        "so there is no sealed state to render and no honest degraded state to "
        "report either"
    ),
    "PROMOTION_AUTHORITY_REFUSED": (
        "a request would have the console decide, select, promote, or expose a "
        "holdout; the console composes read-only panels and confers no evaluator, "
        "holdout or promotion authority"
    ),
    "RECEIPT_DRIFT": (
        "a panel or dashboard receipt does not re-derive its own identifier and "
        "hash, so the record being read is not the record that was emitted"
    ),
    "DASHBOARD_SUBPANEL_TAMPERED": (
        "a panel receipt handed to the dashboard composition does not re-derive "
        "its own identity, so the screen would bind a panel the gate did not emit"
    ),
    "DISHONEST_STATE_REFUSED": (
        "a panel state would present a backend failure as a confirmed emptiness "
        "or a populated finding, which reports that nothing exists when in fact "
        "nothing was read; the gate fails closed rather than emit it"
    ),
    "COMPLETENESS_OVERSTATED": (
        "a dashboard claims a complete screen while a panel it embeds is not "
        "populated, so the operator view would overstate what the console knows"
    ),
}

#: The panel field that names each surface's principal collection in the U05
#: view's ``counts`` map.  Emptiness is decided on this count alone: a challenge
#: board with genomes but no results is empty *of results*, and a front with no
#: candidates is empty *of candidates*.  These are U05's own count keys, not
#: canonical enum vocabulary, so reading one is a structural lookup, not a wire
#: literal (EF4-I22).
_PRINCIPAL_COUNT: dict[str, str] = {
    SURFACE_PARETO_FRONT: "candidates",
    SURFACE_NICHE_MAP: "niches",
    SURFACE_LINEAGES: "lineages",
    SURFACE_CHALLENGE_BOARD: "challenge_results",
}

#: Identifier prefixes.  Every identifier this gate mints is derived from the
#: record's own content, so nothing here needs entropy and two runs over equal
#: inputs produce byte-equal records.
PANEL_ID_PREFIX = "OP-"
DASHBOARD_ID_PREFIX = "OD-"

#: The default role a projection is attributed to when a caller names none.  A
#: role name is not canonical vocabulary; whatever it is, it confers no
#: authority, because the console grants none to anyone.
DEFAULT_REQUESTING_ROLE = "console_reader"


class UsabilityGateError(ValueError):
    """The gate refuses a request, or its evidence, with a documented code."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    if code not in FINDING_CODES:
        raise UsabilityGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise UsabilityGateError(code, message, context)


# -- input shape guards (never mutate the input) --------------------------


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _require_sequence(value: object, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


# -- deterministic identity and deep freezing -----------------------------


def _digest_body(payload: Any) -> str:
    """The hex body of a canonical digest, used to derive content-bound ids."""
    return sha256_of_payload(payload)[len(SHA256_PREFIX) :]


def _freeze(value: Any) -> Any:
    """Deep-freeze a record into read-only mappings and tuples."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Recover a plain, JSON-serializable structure from a frozen record."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _identified(
    record: dict[str, Any], prefix: str, id_field: str, hash_field: str
) -> dict[str, Any]:
    """Attach a content-derived identifier and the record's own hash."""
    record[id_field] = prefix + _digest_body(record)
    record[hash_field] = hash_excluding(record, hash_field)
    return record


def _require_identity(
    record: Mapping[str, Any], prefix: str, id_field: str, hash_field: str, code: str
) -> dict[str, Any]:
    """Re-derive a receipt's identifier and hash from its own content."""
    document = _thaw(_require_mapping(record, "receipt"))
    body = {
        key: value
        for key, value in document.items()
        if key not in {id_field, hash_field}
    }
    derived_id = prefix + _digest_body(body)
    derived_hash = hash_excluding(dict(document), hash_field)
    if document.get(id_field) != derived_id or document.get(hash_field) != derived_hash:
        _fail(
            code,
            "the receipt does not re-derive its own identity",
            {
                "derived_hash": derived_hash,
                "derived_id": derived_id,
                "stated_id": document.get(id_field),
            },
        )
    return document


# -- the honest-state boundary --------------------------------------------


def _guard_honest_state(state: ResultState, *, backend_error: str | None) -> None:
    """Refuse a panel that would present a failure as a finding (EF4-I23).

    The check is delegated to the module that owns the honest-UI vocabulary: an
    ``UNAVAILABLE`` panel may carry a backend error, but a ``POPULATED``,
    ``EMPTY_CONFIRMED`` or ``DEGRADED`` panel that carries one is a failure
    dressed as a research finding, and the sealed owner raises on exactly that.
    """
    try:
        require_honest_state(state, backend_error=backend_error)
    except ResultStateViolation as error:
        _fail(
            "DISHONEST_STATE_REFUSED",
            str(error),
            {"backend_error": backend_error, "state": str(state)},
        )


# -- one operator panel ----------------------------------------------------


def build_operator_panel(
    *,
    surface: str,
    payload: Mapping[str, Any] | None,
    created_at: str,
    current_revision: str | None = None,
    source_revision: str | None = None,
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
    authority_request: object | None = None,
) -> MappingProxyType:
    """Compose one honest operator panel from a sealed U05 surface.

    The authority boundary is checked first and unconditionally.  The surface
    must be one the sealed console declares — an undeclared surface is a
    malformed request, not a degradable panel, so it is refused rather than shown
    as unavailable.  From there the panel is *honest about what happened*:

    * ``payload is None`` — the surface was not supplied, so nothing was read:
      ``UNAVAILABLE``.
    * U05 refuses the surface (tampered, drifted, malformed) — nothing can be
      trusted, so the panel is ``UNAVAILABLE`` and carries the U05 finding code
      as its reason.  A refused upstream is *never* turned into a healthy panel.
    * the surface projects but was built against a superseded revision —
      ``DEGRADED``.
    * the surface projects, is current, and its principal collection is empty —
      ``EMPTY_CONFIRMED``, a real observation distinct from a failure.
    * the surface projects with results — ``POPULATED``.
    """
    role = _require_text(requesting_role, "requesting_role")
    if authority_request is not None:
        _fail(
            "PROMOTION_AUTHORITY_REFUSED",
            "the console composes read-only panels and confers no decision authority",
            {"authority_request": repr(authority_request), "requesting_role": role},
        )
    name = _require_text(surface, "surface")
    if name not in declared_surfaces():
        _fail(
            "SURFACE_UNDECLARED",
            "the sealed console does not project the requested surface",
            {"declared": list(declared_surfaces()), "surface": name},
        )
    timestamp = _require_text(created_at, "created_at")

    state: ResultState
    reason: str
    available: bool
    is_stale: bool = False
    source_view_id: str | None = None
    source_view_hash: str | None = None
    item_count: int | None = None
    finding_code: str | None = None

    if payload is None:
        state = ResultState.UNAVAILABLE
        available = False
        reason = "the surface was not supplied, so nothing was read"
    elif not isinstance(payload, Mapping):
        # A surface supplied in a shape the console cannot read is untrustworthy,
        # not a healthy panel: it becomes an honest UNAVAILABLE rather than a
        # fabricated state or a silently defaulted one.
        state = ResultState.UNAVAILABLE
        available = False
        reason = (
            "the surface was supplied in a shape the console cannot read, so it "
            "cannot be trusted or derived"
        )
    else:
        request = _require_mapping(payload, "payload")
        try:
            view = build_console_projection(
                surface=name, payload=request, requesting_role=role
            )
        except ConsoleProjectionRefused as error:
            state = ResultState.UNAVAILABLE
            available = False
            finding_code = error.code
            reason = (
                f"the sealed console refused the surface ({error.code}), so it "
                "cannot be trusted or derived"
            )
        else:
            source_view_id = str(view["view_id"])
            source_view_hash = str(view["view_hash"])
            item_count = int(view["counts"][_PRINCIPAL_COUNT[name]])
            declared_source = (
                None
                if source_revision is None
                else _require_text(source_revision, "source_revision")
            )
            declared_current = (
                None
                if current_revision is None
                else _require_text(current_revision, "current_revision")
            )
            if (
                declared_current is not None
                and declared_source is not None
                and declared_source != declared_current
            ):
                state = ResultState.DEGRADED
                available = True
                is_stale = True
                reason = (
                    "the panel was built against a superseded revision, so its "
                    "content may no longer reflect the current sealed state"
                )
            elif item_count == 0:
                state = ResultState.EMPTY_CONFIRMED
                available = True
                reason = (
                    "the sealed surface projected and is current, and it holds "
                    "nothing — a confirmed emptiness, not a failure"
                )
            else:
                state = ResultState.POPULATED
                available = True
                reason = "the sealed surface projected and holds results"

    # The honest-state owner refuses a failure dressed as a finding: an
    # UNAVAILABLE panel may carry the failure, no other state may.
    _guard_honest_state(
        state,
        backend_error=reason if state is ResultState.UNAVAILABLE else None,
    )

    panel: dict[str, Any] = {
        "surface": name,
        "state": str(state),
        "available": available,
        "is_stale": is_stale,
        "readonly": True,
        "grants_authority": False,
        "requesting_role": role,
        "reason": reason,
        "finding_code": finding_code,
        "source_view_id": source_view_id,
        "source_view_hash": source_view_hash,
        "item_count": item_count,
        "created_at": timestamp,
    }
    return _freeze(_identified(panel, PANEL_ID_PREFIX, "panel_id", "panel_hash"))


def require_panel_identity(panel: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a panel receipt's identifier and hash from its own content."""
    return _require_identity(
        panel, PANEL_ID_PREFIX, "panel_id", "panel_hash", "RECEIPT_DRIFT"
    )


# -- the composed operator dashboard --------------------------------------


def _completeness(panels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The honest completeness verdict recomputed from panel states.

    ``complete`` is true only when *every* panel is ``POPULATED``: an empty,
    degraded or unavailable panel is a screen the operator cannot read in full,
    and saying otherwise overstates what the console knows.
    """
    populated = str(ResultState.POPULATED)
    unavailable = str(ResultState.UNAVAILABLE)
    degraded = str(ResultState.DEGRADED)
    empty = str(ResultState.EMPTY_CONFIRMED)
    states = [str(panel["state"]) for panel in panels]
    return {
        "complete": bool(panels) and all(state == populated for state in states),
        "unavailable_surfaces": sorted(
            str(panel["surface"])
            for panel in panels
            if str(panel["state"]) == unavailable
        ),
        "degraded_surfaces": sorted(
            str(panel["surface"]) for panel in panels if str(panel["state"]) == degraded
        ),
        "empty_surfaces": sorted(
            str(panel["surface"]) for panel in panels if str(panel["state"]) == empty
        ),
        "state_counts": {
            str(value): states.count(str(value))
            for value in (
                ResultState.POPULATED,
                ResultState.EMPTY_CONFIRMED,
                ResultState.DEGRADED,
                ResultState.UNAVAILABLE,
            )
        },
    }


def compose_operator_dashboard(
    *,
    panels: Sequence[Mapping[str, Any]],
    created_at: str,
    requesting_role: str = DEFAULT_REQUESTING_ROLE,
    authority_request: object | None = None,
) -> MappingProxyType:
    """Bind already-built panel receipts into one honest operator screen.

    The authority boundary is checked first and unconditionally.  Each panel
    receipt is re-derived from its own content, so a tampered panel cannot be
    laundered into the screen (``DASHBOARD_SUBPANEL_TAMPERED``).  The screen's
    ``complete`` flag and its degraded/unavailable rosters are recomputed from
    the panel states the dashboard actually embeds, so the composition can never
    overstate what the operator can see.
    """
    role = _require_text(requesting_role, "requesting_role")
    if authority_request is not None:
        _fail(
            "PROMOTION_AUTHORITY_REFUSED",
            "the console composes read-only panels and confers no decision authority",
            {"authority_request": repr(authority_request), "requesting_role": role},
        )
    timestamp = _require_text(created_at, "created_at")
    rows = _require_sequence(panels, "panels")

    embedded: list[dict[str, Any]] = []
    for position, candidate in enumerate(rows):
        record = _require_identity(
            _require_mapping(candidate, f"panels[{position}]"),
            PANEL_ID_PREFIX,
            "panel_id",
            "panel_hash",
            "DASHBOARD_SUBPANEL_TAMPERED",
        )
        embedded.append(record)
    embedded.sort(key=lambda item: (str(item["surface"]), str(item["panel_id"])))

    completeness = _completeness(embedded)
    dashboard: dict[str, Any] = {
        "readonly": True,
        "grants_authority": False,
        "requesting_role": role,
        "surfaces_requested": [str(panel["surface"]) for panel in embedded],
        "panels": embedded,
        "panel_ids": [str(panel["panel_id"]) for panel in embedded],
        "complete": completeness["complete"],
        "unavailable_surfaces": completeness["unavailable_surfaces"],
        "degraded_surfaces": completeness["degraded_surfaces"],
        "empty_surfaces": completeness["empty_surfaces"],
        "state_counts": completeness["state_counts"],
        "counts": {
            "panels": len(embedded),
            "available": sum(1 for panel in embedded if bool(panel["available"])),
        },
        "created_at": timestamp,
    }
    return _freeze(
        _identified(dashboard, DASHBOARD_ID_PREFIX, "dashboard_id", "dashboard_hash")
    )


def require_dashboard_identity(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a dashboard receipt's identifier and hash from its content."""
    return _require_identity(
        dashboard,
        DASHBOARD_ID_PREFIX,
        "dashboard_id",
        "dashboard_hash",
        "RECEIPT_DRIFT",
    )


def audit_dashboard_completeness(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse a dashboard whose stated completeness overstates its panels.

    Independent of the hash: the completeness verdict is recomputed from the
    panel states the dashboard embeds, so a record whose ``complete`` flag or
    degraded/unavailable rosters were forged to look healthier than the panels
    it carries is refused (``COMPLETENESS_OVERSTATED``), even if its hash was
    resealed to match the forgery.
    """
    record = _thaw(_require_mapping(dashboard, "dashboard"))
    panels = [
        _require_mapping(panel, f"dashboard.panels[{position}]")
        for position, panel in enumerate(
            _require_sequence(record.get("panels"), "dashboard.panels")
        )
    ]
    recomputed = _completeness(panels)
    mismatches = {
        field: {"stated": record.get(field), "recomputed": recomputed[field]}
        for field in (
            "complete",
            "unavailable_surfaces",
            "degraded_surfaces",
            "empty_surfaces",
        )
        if record.get(field) != recomputed[field]
    }
    if mismatches:
        _fail(
            "COMPLETENESS_OVERSTATED",
            "the dashboard's stated completeness does not match its panels",
            {"mismatches": mismatches},
        )
    return record


def declared_panel_surfaces() -> tuple[str, ...]:
    """The surfaces an operator panel can be composed for, in a stable order.

    These are exactly the surfaces the sealed U05 console declares: this gate
    projects nothing the sealed console does not, and invents no surface of its
    own.
    """
    return declared_surfaces()


__all__ = [
    "DASHBOARD_ID_PREFIX",
    "DEFAULT_REQUESTING_ROLE",
    "FINDING_CODES",
    "PANEL_ID_PREFIX",
    "ConsoleProjectionRefused",
    "ResultState",
    "UsabilityGateError",
    "audit_dashboard_completeness",
    "build_console_projection",
    "build_operator_panel",
    "compose_operator_dashboard",
    "declared_panel_surfaces",
    "declared_surfaces",
    "require_dashboard_identity",
    "require_panel_identity",
    "require_view_identity",
]
