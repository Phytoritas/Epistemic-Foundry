"""Provider neutrality (EF4-I34).

Models are replaceable node executors. An adapter may change how a node is
executed but not what the result means, so `assert_semantics_preserved` compares
the canonical fields of a node result across providers and refuses any divergence
in the fields that carry meaning.

The distinction that matters: latency, token counts, and model identity are
expected to differ between providers. Verdicts, statuses, hashes, and evidence
references are not. Allowing an adapter to alter the latter would make the
provider an authority on epistemic content.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: Fields whose values carry canonical meaning. An adapter may not change them.
CANONICAL_RESULT_FIELDS: tuple[str, ...] = (
    "status",
    "verdict",
    "decision",
    "evidence_ids",
    "gate_result_ids",
    "artifact_ids",
    "content_hash",
    "result_hash",
)

#: Fields expected to differ per provider. Divergence here is not a violation.
PROVIDER_LOCAL_FIELDS: frozenset[str] = frozenset(
    {
        "model",
        "model_tier",
        "provider",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_output_tokens",
        "session_id",
        "host_agent_type",
    }
)


class ProviderSemanticsViolation(ValueError):
    """An adapter altered a canonical field."""


def assert_semantics_preserved(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    canonical_fields: Sequence[str] = CANONICAL_RESULT_FIELDS,
) -> None:
    """Raise when `candidate` differs from `reference` on a canonical field.

    Only fields present in the reference are compared, so a provider that omits
    an optional field is not penalized; a provider that *changes* one is.
    """
    divergent: list[str] = []
    for name in canonical_fields:
        if name not in reference:
            continue
        if name not in candidate:
            divergent.append(f"{name} missing from candidate")
        elif reference[name] != candidate[name]:
            divergent.append(f"{name}: {reference[name]!r} != {candidate[name]!r}")
    if divergent:
        raise ProviderSemanticsViolation(
            "adapter altered canonical semantics: "
            + "; ".join(divergent)
            + "; a provider executes nodes but is not an authority on their meaning"
        )


def provider_local_differences(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> list[str]:
    """Fields that differ but are expected to; reported, never refused."""
    return sorted(
        name
        for name in PROVIDER_LOCAL_FIELDS
        if name in reference and name in candidate and reference[name] != candidate[name]
    )
