"""Every way the J06 gate refuses, and every contract it reads rather than restates.

J06 is an *integration gate* (EF4-I22): it composes surfaces other packages
already sealed rather than growing a second copy of their vocabulary.  The
operator/prompt qualification comes from the J05 registry and prompt-workflow
and the S05 inert-mutations gate; the context budget comes from the budget
envelope module and the canonical ``context-assembly-manifest`` schema.  This
module opens the two schemas J06 reads directly — the context assembly manifest
and the budget envelope — and holds nothing about the qualification surfaces,
which the gate reaches through their own imported entry points.

The token-accounting field names and the budget's token dimension are verified
to still be declared by their schemas on every read, so a canonical rename
closes the gate here instead of leaving it metering a field the contract no
longer names.  Nothing in this package scores, selects, promotes or executes.
"""

from __future__ import annotations

from typing import Any, Mapping

from ...contracts import default_registry

#: Canonical schema names.  These are schema *names*, not wire vocabulary.
CONTEXT_MANIFEST_KIND = "context-assembly-manifest"
BUDGET_ENVELOPE_KIND = "budget-envelope"

#: Context-assembly-manifest fields read back out of the schema rather than
#: trusted.  A context budget is measured against ``total_tokens``, which must
#: be re-derivable from the three component fields the schema declares.
TOKEN_ACCOUNTING_FIELD = "token_accounting"
INSTRUCTION_TOKENS_FIELD = "instruction_tokens"
EVIDENCE_TOKENS_FIELD = "evidence_tokens"
TOOL_TOKENS_FIELD = "tool_tokens"
TOTAL_TOKENS_FIELD = "total_tokens"
COMPONENT_TOKEN_FIELDS: tuple[str, ...] = (
    INSTRUCTION_TOKENS_FIELD,
    EVIDENCE_TOKENS_FIELD,
    TOOL_TOKENS_FIELD,
)
MANIFEST_ID_FIELD = "manifest_id"
CONTEXT_HASH_FIELD = "context_hash"

#: Budget-envelope fields.  The enforcement label is never restated here: the
#: budget module's own ``spend_is_bounded`` owns which labels bound spend, and
#: the token ceiling is read through its ``normalize_hard_limits``.
HARD_LIMITS_FIELD = "hard_limits"
TOKENS_DIMENSION = "tokens"
ENFORCEMENT_FIELD = "enforcement"
BUDGET_ID_FIELD = "budget_id"
BUDGET_HASH_FIELD = "budget_hash"

#: Every way this package refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "BUDGET_CONTRACT_DRIFT": (
        "the canonical budget-envelope schema no longer declares the hard-limit "
        "token dimension or the enforcement label this gate meters against, so "
        "the ceiling would be read from a contract that has moved"
    ),
    "BUDGET_MALFORMED": (
        "the budget envelope does not satisfy its canonical schema or its own "
        "digest does not re-derive, so the ceiling it publishes cannot be trusted"
    ),
    "BUDGET_UNENFORCED": (
        "the envelope's enforcement label does not bound spend, or it names no "
        "token ceiling, so admitting work against it would claim a limit that "
        "enforces nothing"
    ),
    "CONTEXT_ACCOUNTING_INCONSISTENT": (
        "the manifest's total token count does not re-derive from its own "
        "instruction, evidence and tool components, so the figure the gate would "
        "meter against is asserted rather than derived"
    ),
    "CONTEXT_CONTRACT_DRIFT": (
        "the canonical context-assembly-manifest schema no longer declares the "
        "token-accounting fields this gate re-derives, so it would meter a shape "
        "the contract no longer names"
    ),
    "CONTEXT_MANIFEST_MALFORMED": (
        "the context assembly manifest does not satisfy its canonical schema, so "
        "the token accounting the gate would meter was never validated"
    ),
    "CONTEXT_OVER_BUDGET": (
        "the work's total context tokens exceed the bounded token ceiling; the "
        "gate refuses work that would overrun the budget rather than truncating "
        "it silently"
    ),
    "GATE_RECEIPT_DRIFT": (
        "the gate receipt does not re-derive its own digest from the fields it "
        "publishes, so it is not the decision the gate actually produced"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "admit an application it never validated"
    ),
    "OPERATOR_UNQUALIFIED": (
        "a prompt-affecting operator binds no qualification evidence, so its "
        "release from quarantine would rest on an assertion rather than on the "
        "artifacts an independent qualification produced"
    ),
    "OPERATOR_UNREGISTERED": (
        "the application names an operator the composed J05 registry does not "
        "hold, and an unregistered operator has no qualification status at all"
    ),
    "PROMPT_QUARANTINED": (
        "the operator's prompt mutation proposal is still held inert by the "
        "quarantine, so applying it would be activation without future-run "
        "qualification (EF4-I55)"
    ),
    "RETROACTIVE_APPLICATION": (
        "the prompt mutation would be applied to the run that produced it, which "
        "is how a run rewrites the judgments it has already received; prompt "
        "mutations apply only to future runs"
    ),
}


class ContextBudgetGateError(ValueError):
    """An operator/prompt qualification or context-budget check refuses admission."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ContextBudgetGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ContextBudgetGateError(code, message, context)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def context_accounting_contract() -> dict[str, Any]:
    """The canonical context-assembly-manifest schema, with its token fields verified.

    The token-accounting sub-fields are read back out of the schema instead of
    trusted, so a rename in the contract fails here rather than leaving the gate
    metering a figure the schema no longer declares.
    """
    document = default_registry().document(CONTEXT_MANIFEST_KIND)
    properties = document.get("properties")
    accounting = (
        properties.get(TOKEN_ACCOUNTING_FIELD)
        if isinstance(properties, Mapping)
        else None
    )
    declared = accounting.get("properties") if isinstance(accounting, Mapping) else None
    declared_fields = set(declared) if isinstance(declared, Mapping) else set()
    required = {TOTAL_TOKENS_FIELD, *COMPONENT_TOKEN_FIELDS}
    missing = sorted(required - declared_fields)
    if missing:
        _fail(
            "CONTEXT_CONTRACT_DRIFT",
            "the canonical context-assembly-manifest schema no longer declares "
            "every token-accounting field this gate re-derives",
            {"missing": missing, "schema": CONTEXT_MANIFEST_KIND},
        )
    return document


def budget_envelope_contract() -> dict[str, Any]:
    """The canonical budget-envelope schema, with its token ceiling verified.

    The hard-limit token dimension and the enforcement label are the two things
    the gate reads from a budget; both are confirmed present so a schema move
    closes the gate instead of silently reading a ceiling that is gone.
    """
    document = default_registry().document(BUDGET_ENVELOPE_KIND)
    properties = document.get("properties")
    properties = properties if isinstance(properties, Mapping) else {}
    limits = properties.get(HARD_LIMITS_FIELD)
    limit_fields = limits.get("properties") if isinstance(limits, Mapping) else None
    limit_declared = set(limit_fields) if isinstance(limit_fields, Mapping) else set()
    missing = sorted(
        {TOKENS_DIMENSION} - limit_declared | ({ENFORCEMENT_FIELD} - set(properties))
    )
    if missing:
        _fail(
            "BUDGET_CONTRACT_DRIFT",
            "the canonical budget-envelope schema no longer declares the token "
            "ceiling or the enforcement label this gate meters against",
            {"missing": missing, "schema": BUDGET_ENVELOPE_KIND},
        )
    return document
