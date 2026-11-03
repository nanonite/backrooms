"""Provider usage metadata, recorded only when the provider actually reports it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UsageMetadata:
    reported: bool
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    actual_cost_usd: float | None
    listed_price_usd: float | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reported": self.reported,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "listed_price_usd": self.listed_price_usd,
            "source": self.source,
        }


def unavailable_usage(listed_price_usd: float | None) -> UsageMetadata:
    return UsageMetadata(
        reported=False,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost_usd=None,
        actual_cost_usd=None,
        listed_price_usd=listed_price_usd,
        source="unavailable",
    )


def usage_from_payload(
    payload: dict[str, Any] | None,
    listed_price_usd: float | None,
    source: str = "provider_response",
) -> UsageMetadata:
    if not isinstance(payload, dict) or not payload:
        return unavailable_usage(listed_price_usd)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else payload
    if usage.get("provider_usage_metadata_reported") is False:
        return unavailable_usage(listed_price_usd)
    input_tokens = _first_int(usage, ("input_tokens", "prompt_tokens"))
    output_tokens = _first_int(usage, ("output_tokens", "completion_tokens"))
    total_tokens = _first_int(usage, ("total_tokens", "actual_token_count"))
    estimated_cost = _first_float(usage, ("estimated_cost_usd", "cost_usd", "cost"))
    actual_cost = _first_float(usage, ("actual_cost_usd",))
    reported = any(
        value is not None
        for value in (
            input_tokens,
            output_tokens,
            total_tokens,
            estimated_cost,
            actual_cost,
        )
    )
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return UsageMetadata(
        reported=reported,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        actual_cost_usd=actual_cost,
        listed_price_usd=listed_price_usd,
        source=source if reported else "unavailable",
    )


def _first_int(payload: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _first_float(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    return None
